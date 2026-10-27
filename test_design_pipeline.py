"""Offline regressions for discovery, grounded content and opposing render specs.
Run: python -m unittest test_design_pipeline
Live checkpoint commands are documented in DESIGN_PIPELINE.md.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import deepseek_website_generator as generator
import pipeline_runner
import preview_dashboard


class DesignPipelineTests(unittest.TestCase):
    business = {"business_name": "Brown's Tree Service", "phone": "(919) 845-6222", "address": "5104 Yachtsman Ct, Raleigh, NC 27615, USA"}

    def test_v7_targets_submitted_link_and_filters_junk(self):
        html = '''<a href="https://cdn.usefathom.com/tracker.js">junk</a>
        <div class="c-item__image"><a href="https://raggededge.com">submitted</a></div>'''
        self.assertEqual(generator.extract_submitted_site(html), "https://raggededge.com")
        for url in ("https://schema.org", "https://www.admiretheweb.com/inspiration/test/", "https://sub.facebook.com", "https://example.com/assets/a", "https://example.com/logo.svg", "javascript:alert(1)", "https://user:password@example.com"):
            self.assertEqual(generator.clean_reference_url(url), "", url)
        self.assertEqual(generator.clean_reference_url("https://example.com/?a=1&amp;b=2"), "https://example.com/?a=1&b=2")

    def test_discovery_returns_four_unique_websites_from_entries(self):
        names = ("Ragged Edge", "North Design", "Geist Studio", "Special Projects")
        urls = ("https://raggededge.com", "https://northdesign.com", "https://geist.studio", "https://www.s-p.studio")
        hub = "".join(f'<article class="c-item"><a href="/inspiration/{i}/">{name}</a></article>' for i, name in enumerate(names))
        def fetch(url, **kwargs):
            if url == generator.ADMIRE_URL:
                return hub, url
            index = int(url.rstrip("/").rsplit("/", 1)[1])
            return f'<div class="c-item__title"><a href="{urls[index]}">Website</a></div>', url
        with patch.object(generator, "fetch_page", side_effect=fetch):
            candidates = generator.discover_reference_websites()
        self.assertEqual([item["url"] for item in candidates], list(urls))
        self.assertTrue(all("/inspiration/" in item["entry_url"] for item in candidates))

    def test_explicit_reference_skips_gallery_discovery(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}", encoding="utf-8")
            analysis = {"schema_version": 2, "reference": {"url": "https://example.com", "selection": "explicit URL"}}
            with patch.object(generator, "discover_reference_websites", side_effect=AssertionError("Explicit URL must skip gallery discovery")), patch.object(generator, "analyze_reference", return_value=analysis):
                output = generator.generate_reference_analysis(handoff, reference_url="https://example.com", rendered=False)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), analysis)
            self.assertEqual(json.loads((folder / "selected_reference.json").read_text(encoding="utf-8"))["url"], "https://example.com")
            self.assertEqual(json.loads((folder / "reference_candidates.json").read_text(encoding="utf-8")), [])

    def test_opposing_specs_change_style_composition_and_order(self):
        light = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
        dark = copy.deepcopy(light)
        dark["colors"].update(background="#101010", text="#FFFFFF", surface="#202020", accent="#FFFFFF", on_accent="#101010")
        dark["hero"]["layout"] = "split"
        dark["layout"]["composition"] = "asymmetric"
        dark["typography"]["heading_family"] = "mono"
        dark["spacing"]["section"] = 160
        dark["components"].update(cards="none", button="outline", radius=20)
        dark["sections"] = [dark["sections"][0], {"type": "local", "layout": "rows", "width": "full-bleed", "tone": "accent"}, dark["sections"][-1]]
        content = generator.verified_business_content(self.business, {}, {})
        first = generator.build_html(self.business, content, light)
        second = generator.build_html(self.business, content, dark)
        css = generator.css_for_design_spec(dark, {"background": "#FF0000"})
        self.assertIn('data-hero="editorial"', first)
        self.assertIn('data-hero="split"', second)
        self.assertIn('data-cards="none"', second)
        self.assertNotIn('id="about"', second)
        self.assertLess(second.index('id="local"'), second.index('id="contact"'))
        for token in ("--bg:#101010", "--section:160px", "--radius:20px", "'Cascadia Code', 'SFMono-Regular', Consolas, monospace"):
            self.assertIn(token, css)
        self.assertNotIn("#FF0000", css)
        self.assertNotIn("__", css)

    def test_handoff_only_omits_invented_services_and_claims(self):
        content = generator.verified_business_content(self.business, {}, {})
        html = generator.build_html(self.business, content, generator.DEFAULT_DESIGN_SPEC)
        for section in ("services", "proof", "reviews", "faq", "process"):
            self.assertNotIn(f'id="{section}"', html)
        self.assertIn("(919) 845-6222", html)
        self.assertIn('href="tel:9198456222"', html)
        self.assertEqual(content["services"], [])
        self.assertEqual(content["proof_points"], [])
        self.assertTrue(content["content_gaps"])

    def test_thin_content_is_expanded_into_useful_local_seo_sections(self):
        research = {
            "business_website": "https://example.com",
            "pages": [{"url": "https://example.com/services", "title": "Services", "text": "Tree removal and pruning services."}],
            "services": ["Tree removal"],
            "service_details": {"Tree removal": "Tree removal is listed as a service. Contact the business to discuss your property and project."},
        }
        generated = {
            "intro": "Brown's Tree Service works in Raleigh and lists tree removal. Share your property details, access needs and goals when you call, and ask what information the team needs to discuss the work and provide an estimate.",
            "services": [{"name": "Tree removal", "description": "Ask Brown's about tree removal for your property. Explain the tree's location, nearby structures, access and the result you want. The team can confirm what information it needs to discuss the scope and whether an on-site estimate is appropriate."}],
            "process": [{"title": f"Step {i}", "text": "Share the project details and confirm the next step with the business before making arrangements."} for i in range(1, 4)],
            "faq": [{"question": f"Question {i}?", "answer": "Contact the business with your address and project details to confirm the service area, availability and next step."} for i in range(1, 5)],
        }
        content = generator.complete_landing_content(generator.verified_business_content(self.business, generated, research), self.business, research)
        spec = generator.ensure_content_sections(generator.DEFAULT_DESIGN_SPEC, content, has_address=True)
        html = generator.build_html(self.business, content, spec, research)
        self.assertIn("seo_title", content)
        self.assertIn("seo_description", content)
        self.assertGreaterEqual(len(content["faq"]), 4)
        self.assertGreaterEqual(len(content["process"]), 3)
        self.assertIn('id="faq"', html)
        self.assertIn('id="process"', html)
        self.assertIn('id="local"', html)
        self.assertIn('"@type": "PostalAddress"', html)
        self.assertIn("Tree removal", html)

    def test_unsafe_tokens_and_inaccessible_colors_are_rejected(self):
        for group, field, value in (("colors", "accent", "red; background:url(evil)"), ("spacing", "section", 99999), ("hero", "layout", "unbounded-html"), ("motion", "duration", float("nan"))):
            spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
            spec[group][field] = value
            with self.assertRaises(ValueError):
                generator.validate_design_spec(spec)
        spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
        spec["colors"]["text"] = "#FFFFFF"
        with self.assertRaises(ValueError):
            generator.css_for_design_spec(spec)
        spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
        spec["sections"][1]["layout"] = "overlap"
        with self.assertRaises(ValueError):
            generator.validate_design_spec(spec)

    def test_non_tree_business_without_images_renders_and_escapes_content(self):
        business = {"business_name": '<script>alert("x")</script>', "phone": "123", "address": "Raleigh, NC"}
        content = generator.verified_business_content(business, {}, {})
        html = generator.build_html(business, content)
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('type="application/ld+json"', html)
        self.assertNotIn('class="hero-image"', html)

    def test_saved_content_survives_reruns_and_cannot_be_reduced_to_contacts(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}", encoding="utf-8")
            (folder / "business.json").write_text(json.dumps(self.business), encoding="utf-8")
            (folder / "reference_analysis.json").write_text(json.dumps({"schema_version": 2, "reference": {"url": "https://example.com"}}), encoding="utf-8")
            spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
            (folder / "design_spec.json").write_text(json.dumps(spec), encoding="utf-8")
            content = generator.verified_business_content(self.business, {}, {})
            content["services"] = [{"name": "Tree removal", "description": "Preserve this supplied service description in full."}]
            content["research_sources"] = ["https://example.com/services"]
            content_file = folder / "supplied_content.json"
            content_file.write_text(json.dumps(content), encoding="utf-8")
            with patch.object(generator, "generate_business_content", side_effect=AssertionError("Must not replace saved copy")), patch.object(generator, "load_or_research_business", side_effect=AssertionError("Must not fetch instead of using supplied copy")):
                output = generator.generate_website(handoff, content_file=content_file)
                original = (output / "index.html").read_bytes()
                self.assertIn(b"Preserve this supplied service description in full.", original)
                original_content = json.loads(content_file.read_text(encoding="utf-8"))
                persisted_content = json.loads((folder / "business_content.json").read_text(encoding="utf-8"))
                original_content.pop("source_mode", None)
                persisted_content.pop("source_mode", None)
                self.assertEqual(persisted_content, original_content)
                persisted_context = json.loads((folder / "design_context.json").read_text(encoding="utf-8"))
                current_context = generator.design_context(self.business, json.loads((folder / "reference_analysis.json").read_text(encoding="utf-8")), False, json.loads((folder / "business_content.json").read_text(encoding="utf-8")))
                self.assertEqual(persisted_context, current_context)
                generator.generate_website(handoff)
                self.assertEqual((output / "index.html").read_bytes(), original)
                with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                    generator.generate_website(handoff, handoff_only=True)
                self.assertEqual((output / "index.html").read_bytes(), original)
                spec["sections"] = [spec["sections"][0], spec["sections"][-1]]
                (folder / "design_spec.json").write_text(json.dumps(spec), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "drop saved content"):
                    generator.generate_website(handoff, content_file=content_file)
                self.assertEqual((output / "index.html").read_bytes(), original)

    def test_new_reference_regenerates_spec_with_saved_content(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}", encoding="utf-8")
            business_file = folder / "business.json"
            business_file.write_text(json.dumps(self.business), encoding="utf-8")
            old_analysis = {"schema_version": 2, "reference": {"url": "https://old.example", "selection": "explicit URL"}}
            (folder / "reference_analysis.json").write_text(json.dumps(old_analysis), encoding="utf-8")
            content = generator.verified_business_content(self.business, {}, {})
            content["research_sources"] = ["https://example.com/services"]
            content["source_mode"] = "supplied source-backed content"
            (folder / "business_content.json").write_text(json.dumps(content), encoding="utf-8")
            (folder / "design_spec.json").write_text(json.dumps(generator.DEFAULT_DESIGN_SPEC), encoding="utf-8")
            (folder / "design_context.json").write_text(json.dumps(generator.design_context(self.business, old_analysis, False, content)), encoding="utf-8")

            def save_new_analysis(handoff_path, reference_index, reference_url, rendered):
                updated = {"schema_version": 2, "reference": {"url": reference_url, "selection": "explicit URL"}}
                (Path(handoff_path).parent / "reference_analysis.json").write_text(json.dumps(updated), encoding="utf-8")

            with patch.object(generator, "generate_reference_analysis", side_effect=save_new_analysis), patch.object(generator, "generate_design_spec") as regenerate_spec:
                generator.generate_website(handoff, reference_url="https://new.example")
            regenerate_spec.assert_called_once()

    def test_pipeline_reads_validator_report_path_and_marks_pass(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}", encoding="utf-8")
            (folder / "business.json").write_text(json.dumps({"business_name": "Sample Business"}), encoding="utf-8")
            website = folder / "website"
            website.mkdir()
            (website / "index.html").write_text("<title>Sample Business</title><h1>Sample Business</h1>", encoding="utf-8")
            (website / "styles.css").write_text("body { color: #222; }", encoding="utf-8")
            (website / "script.js").write_text("document.documentElement.dataset.ready = 'true';", encoding="utf-8")
            with patch.object(pipeline_runner, "generate_website", return_value=website) as generate, patch.object(pipeline_runner, "create_delivery_json") as delivery, patch.object(pipeline_runner, "generate_sales_package"), patch.object(pipeline_runner, "save_status"), patch.object(pipeline_runner, "print", create=True):
                status = pipeline_runner.run_pipeline(folder, reference_url="https://reference.example")
            self.assertEqual(status, "PASS")
            generate.assert_called_once_with(handoff, reference_url="https://reference.example")
            delivery.assert_called_once_with(folder)

    def test_dashboard_builds_named_preview_and_download_routes(self):
        client_folder = Path("codex_handoffs/HIGH/Brown's Tree Service Live Test")
        preview, download = preview_dashboard.landing_page_urls(client_folder)
        self.assertEqual(preview, "/preview/HIGH/Brown%27s%20Tree%20Service%20Live%20Test/index.html")
        self.assertEqual(download, "/download-demo/HIGH/Brown%27s%20Tree%20Service%20Live%20Test")


if __name__ == "__main__":
    unittest.main()
