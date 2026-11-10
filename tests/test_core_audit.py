"""Core workflow regressions using isolated files and mocked providers."""
import concurrent.futures
import json
import os
import tempfile
import unittest
from datetime import datetime
from html import escape
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import api_usage_logger
import batch_logger
import batch_pipeline
import pipeline_runner
import deepseek_website_generator as legacy_generator
import deepseek_website_generator_backup as html_generator
import reference_website_generator as generator
import seo_lead_finder_prospecting_batch as finder
from ai_handoff import build_ai_handoff
from deepseek_response import completion_text
from status_manager import get_status, is_completed, save_status
from test_reference_composition import content, source, spec
from website_validator import validate


def response(text, reason='stop'):
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        choices=[SimpleNamespace(finish_reason=reason, message=SimpleNamespace(content=text))])


class CoreAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def project(self, name='Example'):
        (self.root / 'business.json').write_text(json.dumps({'business_name': name, 'business_type': 'care'}), encoding='utf-8')
        handoff = self.root / 'AI_HANDOFF.json'
        handoff.write_text('{}', encoding='utf-8')
        website = self.root / 'website'
        website.mkdir(exist_ok=True)
        html = f'<html><head><title>{escape(name)}</title><meta name="description" content="Contact the business for details."><meta name="viewport" content="width=device-width"></head><body><h1>{escape(name)}</h1></body></html>'
        for filename, text in [('index.html', html), ('styles.css', 'body{}'), ('script.js', '// saved')]:
            (website / filename).write_text(text, encoding='utf-8')
        return handoff

    def test_validator_accepts_escaped_verified_names_and_still_rejects_claims(self):
        for name in ("A & B Care", "D'Angelo Care", 'Certified Care'):
            with self.subTest(name=name):
                self.project(name)
                report = json.loads(validate(self.root).read_text(encoding='utf-8'))
                self.assertEqual(report['status'], 'PASS', report)
        page = self.root / 'website' / 'index.html'
        page.write_text(page.read_text(encoding='utf-8') + '<p>We are certified and guaranteed.</p>', encoding='utf-8')
        report = json.loads(validate(self.root).read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'NEEDS REVIEW')
        self.assertTrue(any('certified' in warning for warning in report['warnings']))

    def test_repeated_search_preserves_verified_enrichment_for_colliding_names(self):
        for address in ('1 Main St', '2 Main St'):
            lead = finder.Lead(1, 'Same Business', address=address, phone='old phone', opportunity='HIGH')
            directory = finder.write_codex_handoff(lead, self.root, 'care')
            business_file = directory / 'business.json'
            saved = json.loads(business_file.read_text(encoding='utf-8'))
            saved.update(services=['Verified service'], seo={'canonical_url': 'https://example.com/'},
                         design_references=['https://reference.example/'], custom_note=address)
            business_file.write_text(json.dumps(saved), encoding='utf-8')
            lead.phone = 'new phone'
            self.assertEqual(finder.write_codex_handoff(lead, self.root, 'care'), directory)
            updated = json.loads(business_file.read_text(encoding='utf-8'))
            self.assertEqual(updated['phone'], 'new phone')
            for key in ('services', 'seo', 'design_references', 'custom_note'):
                self.assertEqual(updated[key], saved[key])
        records = [json.loads(file.read_text(encoding='utf-8')) for file in self.root.glob('HIGH/*/business.json')]
        self.assertEqual({record['custom_note'] for record in records}, {'1 Main St', '2 Main St'})

    def test_redesign_without_saved_copy_stops_before_a_paid_request(self):
        handoff = self.project()
        before = (self.root / 'website' / 'index.html').read_bytes()
        with patch.object(generator, 'generate_copy') as generate:
            with self.assertRaisesRegex(RuntimeError, 'Saved copy is unavailable'):
                generator.generate_website(handoff, preserve_content=True)
        generate.assert_not_called()
        self.assertEqual((self.root / 'website' / 'index.html').read_bytes(), before)
        self.assertFalse((self.root / 'GENERATED_COPY.json').exists())

    def test_changed_priority_moves_saved_website_without_overwriting_another_business(self):
        lead = finder.Lead(1, 'Same Business', address='1 Main St', opportunity='HIGH')
        previous = finder.write_codex_handoff(lead, self.root, 'care')
        (previous / 'website').mkdir()
        (previous / 'website' / 'index.html').write_text('Saved website', encoding='utf-8')
        (previous / 'GENERATED_COPY.json').write_text('{"headline":"Approved copy"}', encoding='utf-8')
        other = finder.Lead(2, 'Same Business', address='2 Main St', opportunity='MEDIUM')
        other_folder = finder.write_codex_handoff(other, self.root, 'care')
        other_before = (other_folder / 'business.json').read_bytes()
        lead.opportunity = 'MEDIUM'
        moved = finder.write_codex_handoff(lead, self.root, 'care')
        self.assertNotEqual(moved, other_folder)
        self.assertFalse(previous.exists())
        self.assertEqual((moved / 'website' / 'index.html').read_text(encoding='utf-8'), 'Saved website')
        self.assertEqual((moved / 'GENERATED_COPY.json').read_text(encoding='utf-8'), '{"headline":"Approved copy"}')
        self.assertEqual((other_folder / 'business.json').read_bytes(), other_before)
        lead.opportunity = 'LOW'
        low = finder.write_codex_handoff(lead, self.root, 'care')
        self.assertFalse(moved.exists())
        self.assertEqual((low / 'website' / 'index.html').read_text(encoding='utf-8'), 'Saved website')
        self.assertEqual(len(list(self.root.glob('*/*/business.json'))), 2)

    def test_search_run_refreshes_existing_handoff_when_priority_becomes_low(self):
        handoffs = self.root / 'handoffs'
        original = finder.Lead(1, 'Returning business', address='1 Main St', opportunity='HIGH')
        previous = finder.write_codex_handoff(original, handoffs, 'care')
        build_ai_handoff(previous / 'business.json')
        fresh = finder.Lead(1, original.name, address=original.address, website='https://example.com/',
                            opportunity='LOW', website_status='working', reason='no major issues detected')
        events = []
        with patch.dict(os.environ, {'GOOGLE_MAPS_API_KEY': 'test-only'}), patch.object(
            finder, 'google_places_search', return_value=[fresh]
        ), patch.object(finder, 'enrich_lead'), patch.object(finder.time, 'sleep'):
            finder.run('care', 'Test area', 'leads.csv', 1, output_dir=self.root / 'outputs',
                       codex_dir=handoffs, progress_callback=events.append)
        updated = handoffs / 'LOW' / original.name
        self.assertFalse(previous.exists())
        self.assertEqual(json.loads((updated / 'AI_HANDOFF.json').read_text())['lead']['priority'], 'LOW')
        self.assertEqual(len(list(handoffs.glob('*/*/business.json'))), 1)
        self.assertEqual((events[-1]['phase'], events[-1]['total'], events[-1]['low']), ('Complete', 1, 1))
        self.assertIn('Returning business', (self.root / 'outputs' / 'care - Test area.csv').read_text())

    def test_failed_rebuild_restores_website_and_copy_but_remains_failed(self):
        for failure in ('render', 'write', 'validation'):
            with self.subTest(failure=failure):
                self.project()
                copy_file = self.root / 'GENERATED_COPY.json'
                copy_file.write_text('{"headline":"Approved copy"}', encoding='utf-8')
                (self.root / 'DELIVERY.json').write_text('{"website_status":"PASS"}', encoding='utf-8')
                before_html = (self.root / 'website' / 'index.html').read_bytes()
                before_copy = copy_file.read_bytes()
                def generate(*args, **kwargs):
                    (self.root / 'website' / 'index.html').write_text('Incomplete replacement', encoding='utf-8')
                    (self.root / 'website' / 'extra.txt').write_text('New asset', encoding='utf-8')
                    copy_file.write_text('{"headline":"Replacement"}', encoding='utf-8')
                    if failure != 'validation':
                        raise (RuntimeError('render failure') if failure == 'render' else OSError('write failure'))
                    return self.root / 'website'
                report = self.root / 'quality_report.json'
                report.write_text('{"status":"NEEDS REVIEW"}', encoding='utf-8')
                with patch.object(pipeline_runner, 'generate_website', side_effect=generate), patch.object(pipeline_runner, 'validate', return_value=report):
                    if failure == 'validation':
                        self.assertEqual(pipeline_runner.run_pipeline(self.root), 'FAILED')
                    else:
                        with self.assertRaisesRegex((RuntimeError, OSError), 'failure'):
                            pipeline_runner.run_pipeline(self.root)
                self.assertEqual((self.root / 'website' / 'index.html').read_bytes(), before_html)
                self.assertEqual(copy_file.read_bytes(), before_copy)
                self.assertFalse((self.root / 'website' / 'extra.txt').exists())
                self.assertEqual(get_status(self.root)['status'], 'FAILED')
                self.assertFalse((self.root / 'DELIVERY.json').exists())
                self.assertEqual(list(self.root.glob('.build-backup-*')), [])

    def test_backup_does_not_follow_a_linked_website_folder(self):
        self.project()
        website = self.root / 'website'
        website.rename(self.root / 'original-website')
        try:
            website.symlink_to(self.root / 'original-website', target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Directory symlinks are unavailable: {error}')
        with patch.object(pipeline_runner, 'generate_website') as generate:
            with self.assertRaisesRegex(RuntimeError, 'linked elsewhere'):
                pipeline_runner.run_pipeline(self.root)
        generate.assert_not_called()
        self.assertTrue((self.root / 'original-website' / 'index.html').is_file())

    def test_failed_restore_keeps_recoverable_backup(self):
        self.project()
        before = (self.root / 'website' / 'index.html').read_bytes()
        rename = Path.rename
        def fail_restore(path, destination):
            if path.parent.name.startswith('.build-backup-'):
                raise OSError('simulated restore failure')
            return rename(path, destination)
        with patch.object(pipeline_runner, 'generate_website', side_effect=RuntimeError('generation failed')), patch.object(Path, 'rename', fail_restore):
            with self.assertRaisesRegex(RuntimeError, 'backup is kept at'):
                pipeline_runner.run_pipeline(self.root)
        backups = list(self.root.glob('.build-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'website' / 'index.html').read_bytes(), before)
        self.assertEqual(get_status(self.root)['status'], 'FAILED')

    def test_failed_render_keeps_previous_approved_copy(self):
        handoff = self.project()
        approved = self.root / 'GENERATED_COPY.json'
        approved.write_text(json.dumps({'headline': 'Approved copy', 'design_spec': {}}), encoding='utf-8')
        before = approved.read_bytes()
        with patch.object(generator, 'generate_copy', return_value={'headline': 'Replacement copy', 'design_spec': {}}), patch.object(
            generator, 'build_html', side_effect=RuntimeError('simulated render failure')
        ):
            with self.assertRaisesRegex(RuntimeError, 'simulated render failure'):
                generator.generate_website(handoff)
        self.assertEqual(approved.read_bytes(), before)

    def test_cutoff_and_interrupted_completions_are_rejected_before_parsing(self):
        for reason in ('length', 'aborted', 'insufficient_system_resource', 'content_filter'):
            for text in ('{"valid":"looking JSON"}', None):
                with self.subTest(reason=reason, text=text):
                    with self.assertRaisesRegex(RuntimeError, 'cut short|stopped before completing'):
                        completion_text(response(text, reason))
        for text in (None, '', '  '):
            with self.subTest(empty=text):
                with self.assertRaisesRegex(RuntimeError, 'empty response'):
                    completion_text(response(text))
        with self.assertRaisesRegex(RuntimeError, 'no completion'):
            completion_text(SimpleNamespace(choices=[]))
        self.assertEqual(completion_text(response('{"ok":true}')), '{"ok":true}')

    def test_all_deepseek_generators_use_supported_model_and_non_thinking(self):
        handoff = self.project()
        for module, invoke in (
            (generator, lambda: generator.generate_copy({'business_name': 'Example'}, {})),
            (legacy_generator, lambda: legacy_generator.generate_copy({'business_name': 'Example'}, {})),
            (html_generator, lambda: html_generator.generate_website(handoff)),
        ):
            with self.subTest(generator=module.__name__):
                client = Mock()
                client.chat.completions.create.return_value = response('{}', 'length')
                with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only'}), patch.object(module, 'OpenAI', return_value=client), patch.object(
                    module, 'log_usage'
                ), patch.object(generator, 'get_reference_research', return_value=[source()]):
                    with self.assertRaisesRegex(RuntimeError, 'cut short'):
                        invoke()
                self.assertEqual(client.chat.completions.create.call_count, 1)
                request = client.chat.completions.create.call_args.kwargs
                self.assertEqual(request['model'], 'deepseek-flash')
                self.assertEqual(request['extra_body'], {'thinking': {'type': 'disabled'}})

    def test_composition_cutoff_does_not_accept_json_or_charge_a_repair_retry(self):
        client = Mock()
        client.chat.completions.create.return_value = response(json.dumps({'page_blueprint': spec()['page_blueprint']}), 'length')
        with patch.object(generator, 'log_usage'):
            with self.assertRaisesRegex(RuntimeError, 'cut short'):
                generator.generate_composition(client, spec(), source(), content(spec()), {'business_name': 'Example'})
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_usage_logging_failure_does_not_fail_a_valid_composition(self):
        client = Mock()
        client.chat.completions.create.return_value = response(json.dumps({'page_blueprint': spec()['page_blueprint']}))
        with patch.object(generator, 'log_usage', side_effect=OSError('simulated unwritable log')):
            result = generator.generate_composition(client, spec(), source(), content(spec()), {'business_name': 'Example'})
        self.assertEqual(result, spec()['page_blueprint'])
        self.assertEqual(client.chat.completions.create.call_count, 1)
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request['model'], 'deepseek-flash')
        self.assertEqual(request['extra_body'], {'thinking': {'type': 'disabled'}})

    def test_concurrent_usage_records_are_kept_and_file_remains_valid_json(self):
        logs = self.root / 'logs'
        with patch.object(api_usage_logger, 'Path', return_value=logs):
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                list(pool.map(lambda index: api_usage_logger.log_usage(f'client-{index}', response('').usage), range(60)))
        records = json.loads((logs / 'api_usage.json').read_text(encoding='utf-8'))
        self.assertEqual({record['client'] for record in records}, {f'client-{index}' for index in range(60)})
        self.assertEqual(len(records), 60)
        self.assertEqual(list(logs.glob('*.tmp')), [])

    def test_failed_usage_save_keeps_previous_log(self):
        logs = self.root / 'logs'
        with patch.object(api_usage_logger, 'Path', return_value=logs):
            api_usage_logger.log_usage('first', response('').usage)
            before = (logs / 'api_usage.json').read_bytes()
            with patch.object(api_usage_logger.os, 'replace', side_effect=OSError('simulated replace failure')):
                with self.assertRaises(OSError):
                    api_usage_logger.log_usage('second', response('').usage)
        self.assertEqual((logs / 'api_usage.json').read_bytes(), before)
        self.assertEqual(list(logs.glob('*.tmp')), [])

    def test_batch_runs_started_together_keep_separate_logs(self):
        with patch.object(batch_logger, 'Path', return_value=self.root), patch.object(batch_logger, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 10, 12, 0, 0)
            first, second = batch_logger.BatchLogger(), batch_logger.BatchLogger()
        self.assertNotEqual(first.run_dir, second.run_dir)
        first.add_completed(Path('first client'))
        second.add_failed(Path('second client'), ValueError('test failure'))
        first.save()
        second.save()
        self.assertEqual(json.loads((first.run_dir / 'summary.json').read_text())['completed'], 1)
        self.assertEqual(json.loads((second.run_dir / 'summary.json').read_text())['failed'], 1)

    def test_resume_retries_corrupt_status_and_incomplete_websites(self):
        self.project()
        status = self.root / 'STATUS.json'
        for value in ('{partial', '[]'):
            status.write_text(value, encoding='utf-8')
            self.assertIsNone(get_status(self.root))
            with patch.object(batch_pipeline, 'run_pipeline', return_value='PASS') as run, patch.object(batch_pipeline, 'BatchLogger'):
                self.assertEqual(batch_pipeline.run_batch([self.root], resume=True), 0)
            run.assert_called_once_with(self.root)
        save_status(self.root, 'PASS')
        self.assertTrue(is_completed(self.root))
        (self.root / 'website' / 'script.js').write_text('', encoding='utf-8')
        self.assertFalse(is_completed(self.root))
        with patch.object(batch_pipeline, 'run_pipeline', return_value='PASS') as run, patch.object(batch_pipeline, 'BatchLogger'):
            batch_pipeline.run_batch([self.root], resume=True)
        run.assert_called_once_with(self.root)


if __name__ == '__main__':
    unittest.main()
