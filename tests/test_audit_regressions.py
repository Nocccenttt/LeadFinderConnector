import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import batch_pipeline
import pipeline_runner
import preview_dashboard as dashboard
import seo_lead_finder_prospecting_batch as finder
from ai_handoff import build_ai_handoff
from deepseek_website_generator import build_html
from delivery_package_builder import build_package
from status_manager import get_status


class PipelineTests(unittest.TestCase):
    def test_pipeline_generates_validates_and_prepares_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "business.json").write_text(json.dumps({
                "business_name": "Example Tree Care", "business_type": "tree service",
                "address": "1 Main St, Dallas, TX", "phone": "555-0100",
            }))
            build_ai_handoff(folder / "business.json")
            with patch("reference_website_generator.download_stock_image", return_value="test.jpg"), patch("reference_website_generator.generate_copy", return_value={
                "headline": "Contact Example Tree Care",
                "seo": {"meta_description": "Contact Example Tree Care to ask about available tree care services in Dallas."},
            }):
                result = pipeline_runner.run_pipeline(folder)
            self.assertEqual(result, "PASS", (folder / "quality_report.json").read_text())
            self.assertEqual(get_status(folder)["status"], "PASS")
            self.assertEqual(json.loads((folder / "quality_report.json").read_text())["status"], "PASS")
            self.assertTrue((folder / "DELIVERY.json").is_file())
            self.assertTrue((folder / "DEMO_PACKAGE" / "Sales" / "OFFER.json").is_file())

    def test_delivery_package_includes_nested_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            assets = folder / "website" / "assets"
            assets.mkdir(parents=True)
            (assets / "logo.svg").write_text("<svg></svg>")
            package = build_package(folder)
            self.assertEqual((package / "Website" / "assets" / "logo.svg").read_text(), "<svg></svg>")

    def test_batch_records_validation_failure_and_continues(self):
        logger = Mock()
        with tempfile.TemporaryDirectory() as temp:
            clients = [Path(temp) / name for name in ("bad", "good")]
            for client in clients:
                client.mkdir()
            with patch.object(batch_pipeline, "BatchLogger", return_value=logger), patch.object(
                batch_pipeline, "run_pipeline", side_effect=["FAILED", "PASS"]
            ):
                failures = batch_pipeline.run_batch(clients)
            self.assertEqual(failures, 1)
            self.assertEqual(get_status(clients[0])["status"], "FAILED")
            self.assertEqual(get_status(clients[1])["status"], "PASS")
            logger.add_failed.assert_called_once()
            logger.add_completed.assert_called_once_with(clients[1])

    def test_generation_exception_invalidates_previous_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "AI_HANDOFF.json").write_text("{}")
            (folder / "DELIVERY.json").write_text('{"website_status":"PASS"}')
            with patch.object(pipeline_runner, "generate_website", side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    pipeline_runner.run_pipeline(folder)
            self.assertEqual(get_status(folder)["status"], "FAILED")
            self.assertFalse((folder / "DELIVERY.json").exists())

    def test_failed_validation_does_not_create_sales_package(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "AI_HANDOFF.json").write_text("{}")
            report = folder / "quality_report.json"
            report.write_text('{"status":"NEEDS REVIEW"}')
            with patch.object(pipeline_runner, "generate_website"), patch.object(
                pipeline_runner, "validate", return_value=report
            ), patch.object(pipeline_runner, "generate_sales_package") as sales:
                self.assertEqual(pipeline_runner.run_pipeline(folder), "FAILED")
                sales.assert_not_called()


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.handoffs = self.root / "codex_handoffs"
        self.name = "A-B #1 & Tree Care"
        self.folder = self.handoffs / "HIGH" / self.name
        website = self.folder / "website"
        website.mkdir(parents=True)
        self.folder.joinpath("AI_HANDOFF.json").write_text("{}")
        self.folder.joinpath("business.json").write_text(json.dumps({
            "business_name": "A/B #1 & Tree Care", "opportunity": "HIGH",
            "website": "javascript:alert(1)", "opportunity_score": 90,
        }))
        for filename, content in {"index.html": '<link rel="stylesheet" href="styles.css">',
                                  "styles.css": "body{color:red}", "script.js": "console.log('demo')"}.items():
            website.joinpath(filename).write_text(content)
        self.addCleanup(patch.stopall)
        patch.object(dashboard, "ROOT", self.root).start()
        patch.object(dashboard, "HANDOFFS", self.handoffs).start()
        patch.object(dashboard, "jobs", {}).start()
        self.client = dashboard.app.test_client()

    def lead(self):
        return self.client.get("/leads").get_json()["leads"][0]

    def test_encoded_preview_loads_html_and_relative_assets(self):
        lead = self.lead()
        self.assertEqual(lead["client_id"], self.name)
        self.assertEqual(lead["website"], "")
        self.assertIn("%23", lead["demo_url"])
        self.assertTrue(lead["demo_url"].endswith("/"))
        with self.client.get(lead["demo_url"]) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"styles.css", response.data)
        with self.client.get(lead["demo_url"] + "styles.css") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"color:red", response.data)

    def test_download_contains_complete_website(self):
        with self.client.get(self.lead()["download_url"]) as response:
            self.assertEqual(response.status_code, 200)
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                self.assertEqual(set(archive.namelist()), {"index.html", "styles.css", "script.js"})

    def test_legacy_preview_and_assets_still_work(self):
        url = self.lead()["demo_url"].replace("/demo/", "/demo/codex_handoffs/")
        for path in (url.rstrip("/"), url + "styles.css"):
            with self.client.get(path, follow_redirects=True) as response:
                self.assertEqual(response.status_code, 200)

    def test_traversal_and_arbitrary_legacy_paths_are_rejected(self):
        outside = self.root / "outside"
        outside.joinpath("website").mkdir(parents=True)
        outside.joinpath("website", "index.html").write_text("private")
        outside.joinpath("AI_HANDOFF.json").write_text("{}")
        for name in ("../../outside", str(outside), "../HIGH", "..\\..\\outside"):
            self.assertIsNone(dashboard.resolve_client("HIGH", name))
        for url in ("/demo/../outside/", "/demo/outside/index.html", "/download-demo/outside",
                    self.lead()["demo_url"] + "../business.json"):
            self.assertEqual(self.client.get(url, follow_redirects=True).status_code, 404, url)

    def test_landing_job_reports_failed_validation(self):
        with patch.object(dashboard, "run_pipeline", return_value="FAILED"):
            dashboard.run_landing_page("bad", self.folder)
        self.assertEqual(dashboard.jobs["bad"]["status"], "error")
        self.assertNotIn("preview_url", dashboard.jobs["bad"])

    def test_landing_job_returns_working_preview_url(self):
        with patch.object(dashboard, "run_pipeline", return_value="PASS"):
            dashboard.run_landing_page("good", self.folder)
        job = dashboard.jobs["good"]
        self.assertEqual(job["status"], "complete")
        with self.client.get(job["preview_url"]) as response:
            self.assertEqual(response.status_code, 200)

    def test_design_only_job_preserves_content_in_pipeline(self):
        with patch.object(dashboard, "run_pipeline", return_value="PASS") as pipeline:
            dashboard.run_landing_page("design-only", self.folder, preserve_content=True)
        pipeline.assert_called_once_with(self.folder, preserve_content=True)

    def test_missing_api_key_sets_terminal_error(self):
        with patch.dict(os.environ, {}, clear=True):
            dashboard.run_generation("missing", "tree service", "City", 1)
        self.assertEqual(dashboard.jobs["missing"]["status"], "error")
        self.assertIn("GOOGLE_MAPS_API_KEY", dashboard.jobs["missing"]["message"])

    def test_invalid_json_shape_returns_bad_request(self):
        for url in ("/generate", "/generate-landing-page"):
            self.assertEqual(self.client.post(url, json=["unexpected"]).status_code, 400)

    def test_duplicate_landing_generation_is_rejected(self):
        with patch.object(dashboard, "Thread") as thread:
            payload = {"priority": "HIGH", "name": self.name}
            self.assertEqual(self.client.post("/generate-landing-page", json=payload).status_code, 200)
            self.assertEqual(self.client.post("/generate-landing-page", json=payload).status_code, 409)
            self.assertEqual(thread.call_count, 1)


class LeadFinderTests(unittest.TestCase):
    def test_same_name_different_addresses_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            first = finder.Lead(1, "Tree Care", address="1 Main St", opportunity="HIGH")
            second = finder.Lead(2, "Tree Care", address="2 Main St", opportunity="HIGH")
            a = finder.write_codex_handoff(first, temp)
            b = finder.write_codex_handoff(second, temp)
            self.assertNotEqual(a, b)
            self.assertEqual(finder.write_codex_handoff(second, temp), b)
            self.assertEqual(json.loads((a / "business.json").read_text())["address"], "1 Main St")

    def test_handoff_preserves_reason_priority_and_email_source(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = finder.write_codex_handoff(finder.Lead(
                1, "Tree Care", opportunity="HIGH", reason="no website",
                email_source_url="https://example.com/contact"), temp)
            result = json.loads(build_ai_handoff(folder / "business.json").read_text())
            self.assertEqual(result["lead"]["priority"], "HIGH")
            self.assertEqual(result["lead"]["reason"], "no website")
            self.assertEqual(result["verified_online_presence"]["email_source_url"], "https://example.com/contact")

    def test_website_inspection_uses_exact_supplied_page(self):
        response = Mock(status_code=200, url="https://example.com/business")
        response.text = '<meta name="viewport" content="width=device-width"><p>Contact us. Phone.</p>'
        with patch.object(finder, "fetch", side_effect=[response] + [None] * 6) as fetch:
            result = finder.inspect_website("https://example.com/business")
        self.assertEqual(fetch.call_args_list[0].args[0], "https://example.com/business")
        self.assertEqual(fetch.call_count, 7)
        self.assertTrue(result["mobile_meta"])
        self.assertTrue(result["cta"])

    def test_repeated_pagination_token_terminates(self):
        response = Mock()
        response.json.return_value = {"places": [{"displayName": {"text": "Same"}}], "nextPageToken": "repeat"}
        with patch.object(finder.requests, "post", return_value=response) as post:
            result = finder.google_places_search("tree", "City", "dummy", 20)
        self.assertEqual(len(result), 1)
        self.assertEqual(post.call_count, 2)

    def test_windows_reserved_and_empty_filenames_are_safe(self):
        self.assertEqual(finder.safe_filename("CON"), "_CON")
        self.assertEqual(finder.safe_filename("..."), "business")

    def test_nullable_generated_fields_do_not_crash_renderer(self):
        html = build_html({"business_name": "Tree Care"}, {
            "services": None, "benefits": None, "process": {}, "faq": None,
            "intro": None, "headline": None,
        })
        self.assertIn("Tree Care", html)
        self.assertNotIn(">None<", html)


if __name__ == "__main__":
    unittest.main()
