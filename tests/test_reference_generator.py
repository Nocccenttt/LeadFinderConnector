import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline_runner
import reference_website_generator as generator
from website_validator import validate


class ReferenceGeneratorTests(unittest.TestCase):
    def test_current_business_type_schema_is_used_instead_of_business_name(self):
        business = {"business_name": "Example", "business_type": "tree service", "address": "1 Main St, Raleigh, NC 27615"}
        self.assertEqual(generator.get_niche(business, {}), "tree service")
        copy = generator.guard_sparse_business_copy({}, business, {})
        self.assertEqual(copy["headline"], "Tree Service in Raleigh, NC")

    def test_sparse_leads_cannot_publish_invented_services_or_process_promises(self):
        result = generator.guard_sparse_business_copy({
            "subheadline": "We provide stump grinding", "services": [{"name": "Stump grinding"}],
            "process": [{"title": "We guarantee cleanup"}], "design_spec": {"hero_style": "Full-width"},
        }, {"business_name": "Example", "business_type": "tree service"}, {})
        self.assertEqual(result["services"], [])
        self.assertNotIn("stump grinding", str(result).lower())
        self.assertNotIn("guarantee cleanup", str(result).lower())
        self.assertEqual(result["design_spec"]["hero_style"], "Full-width")

    def test_dashboard_pipeline_uses_archived_generator(self):
        self.assertIs(pipeline_runner.generate_website, generator.generate_website)

    def test_extractor_uses_submitted_site_instead_of_analytics_script(self):
        html = '''<script src="https://cdn.usefathom.com/script.js"></script>
        <figure class="c-item__image"><a href="https://example.com/"><img></a></figure>'''
        self.assertEqual(generator._extract_submitted_site(html), "https://example.com/")

    def test_research_fetches_actual_site_and_passes_expected_schema(self):
        discovery = {"references": [{"url": "https://admiretheweb.com/inspiration/example/"}], "note": "Candidate"}
        def fetch(url, max_chars):
            if "admiretheweb.com" in url:
                return '<h1 class="c-item__title"><a href="https://example.com/">Example</a></h1>'
            return '<title>Example</title><style>body{color:#123456;font-family:Arial;display:grid}</style><h1>Actual site</h1>'
        with patch.object(generator, "discover_admire_references", return_value=discovery), patch.object(
            generator, "fetch_reference_page", side_effect=fetch
        ):
            candidate = generator.get_reference_research({"business_type": "tree service"}, {})[0]
        self.assertEqual(candidate["website_url"], "https://example.com/")
        self.assertEqual(candidate["hub_url"], discovery["references"][0]["url"])
        self.assertIn("Actual site", candidate["website_headings"])
        self.assertIn("#123456", candidate["style_signals"]["frequent_hex_colors"])

    def test_research_discards_expired_sites_that_redirect_to_domain_sales(self):
        discovery = {"references": [{"url": "https://admiretheweb.com/inspiration/parked/"}]}
        with patch.object(generator, "discover_admire_references", return_value=discovery), patch.object(
            generator, "fetch_reference_page", side_effect=[
                '<h1 class="c-item__title"><a href="https://expired.example/">Old site</a></h1>',
                '<title>DomainAgents - Domain Name Broker and Marketplace</title>',
            ]
        ):
            with self.assertRaisesRegex(RuntimeError, "No actual reference"):
                generator.get_reference_research({"business_type": "pet grooming"}, {})

    def test_renderer_applies_section_order_composition_and_one_hero(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(generator, "download_stock_image", return_value="photo.jpg"):
            html = generator.build_html({"business_name": "Example"}, {
                "design_spec": {"section_order": ["faq", "about", "cta"],
                                "composition": {"about": "editorial"}},
                "faq": [{"question": "How do I contact Example?", "answer": "Call the business."}],
            }, "tree service", Path(temp))
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(soup.select("h1")), 1)
        sections = soup.select("main > section")
        self.assertIn("hero", sections[0].get("class", []))
        self.assertIn("composition-editorial", str(soup))
        self.assertLess(html.index('id="faq"'), html.index('id="about"'))

    def test_prose_composition_choices_reach_renderer_and_sans_is_not_serif(self):
        spec = generator.normalize_design_spec({"composition": {
            "about": "Split-media with text left and image right.",
            "services": "Editorial list with alternating text rows.",
        }})
        self.assertEqual(spec["composition"]["about"], "split-media")
        self.assertEqual(spec["composition"]["services"], "editorial")
        css = generator.build_design_css({"typography_style": "Single sans-serif family"})
        self.assertIn("--font-heading: Arial, Helvetica, sans-serif", css)

    def test_validator_ignores_css_hex_but_flags_visible_claims(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "business.json").write_text(json.dumps({"business_name": "Example"}))
            website = root / "website"
            website.mkdir()
            (website / "styles.css").write_text("body{color:#172019}")
            (website / "script.js").write_text("// nothing")
            html = '''<title>Example</title><meta name="description" content="Example services">
            <meta name="viewport" content="width=device-width"><style>body{color:#172019}</style>
            <h1>Example</h1>'''
            path = website / "index.html"
            path.write_text(html)
            report = json.loads(validate(root).read_text())
            self.assertFalse(any("unsupported claim" in warning for warning in report["warnings"]))
            path.write_text(html + "<p>We are #1</p>")
            report = json.loads(validate(root).read_text())
            self.assertTrue(any("unsupported claim" in warning for warning in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
