"""Regression tests for LeadFinder's scrape-to-landing-page path."""

import sys
import unittest
from unittest.mock import Mock, patch

import pipeline_runner
from deepseek_website_generator import build_html
from seo_lead_finder_prospecting_batch import google_places_search
from website_planning import (build_css_theme, build_design_blueprint, build_seo_strategy, choose_layout_variant, discover_admire_references, validate_seo_html)


class PipelineExitStatusTests(unittest.TestCase):
    def test_failed_pipeline_returns_nonzero_exit(self):
        with patch.object(sys, "argv", ["pipeline_runner.py", "client-folder"]):
            with patch("pipeline_runner.run_pipeline", return_value="FAILED"):
                with self.assertRaises(SystemExit) as raised:
                    pipeline_runner.main()
        self.assertEqual(raised.exception.code, 1)

    def test_passed_pipeline_returns_normally(self):
        with patch.object(sys, "argv", ["pipeline_runner.py", "client-folder"]):
            with patch("pipeline_runner.run_pipeline", return_value="PASS"):
                pipeline_runner.main()


class GooglePlacesPaginationTests(unittest.TestCase):
    @patch("seo_lead_finder_prospecting_batch.requests.post")
    def test_fetches_multiple_pages_and_deduplicates(self, post):
        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "places": [
                {"displayName": {"text": "Alpha Plumbing"}, "formattedAddress": "1 Main St"},
                {"displayName": {"text": "Beta Plumbing"}, "formattedAddress": "2 Main St"},
            ],
            "nextPageToken": "next-page",
        }
        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {
            "places": [
                {"displayName": {"text": "Beta Plumbing"}, "formattedAddress": "2 Main St"},
                {"displayName": {"text": "Gamma Plumbing"}, "formattedAddress": "3 Main St"},
            ]
        }
        post.side_effect = [first, second]

        leads = google_places_search("plumber", "Example City", "test-key", 3)

        self.assertEqual([lead.name for lead in leads], [
            "Alpha Plumbing", "Beta Plumbing", "Gamma Plumbing"
        ])
        self.assertEqual([lead.maps_position for lead in leads], [1, 2, 3])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["pageToken"], "next-page")

    @patch("seo_lead_finder_prospecting_batch.requests.post")
    def test_zero_limit_does_not_call_api(self, post):
        self.assertEqual(google_places_search("plumber", "Example City", "test-key", 0), [])
        post.assert_not_called()


class LandingPageCategoryTests(unittest.TestCase):
    def test_html_applies_selected_layout_class(self):
        html = build_html(
            {"business_name": "Example Tree Care", "business_type": "tree service"},
            {},
            {},
            {"layout_variant": "service-first"},
        )
        self.assertIn('<body class="layout-service-first">', html)

    def test_html_uses_supplied_business_category(self):
        html = build_html(
            {
                "business_name": "Example Tree Care",
                "business_type": "tree service",
                "phone": "555-0100",
                "address": "1 Main St, Example City",
            },
            {},
        )
        self.assertIn("Tree Service", html)
        self.assertIn("Example Tree Care", html)
        self.assertNotIn("Junk Removal", html)
        self.assertNotIn("junk removal", html.lower())
        self.assertNotIn("CLEAR SPACE", html)
        self.assertIn("BUILT AROUND", html)




class DesignResearchTests(unittest.TestCase):
    @patch("website_planning.requests.get")
    def test_reference_search_extracts_only_real_admire_domains(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = """
        <article><h2><a href="https://www.admiretheweb.com/example-design/">Example Design</a></h2><p>Bold typography and strong hierarchy.</p></article>
        <article><h2><a href="https://admiretheweb.com/another/">Another Design</a></h2></article>
        <article><h2><a href="https://admiretheweb.com.attacker.invalid/fake/">Fake Domain</a></h2></article>
        """
        get.return_value = response

        result = discover_admire_references("tree service")

        self.assertEqual(result["status"], "found")
        self.assertEqual(len(result["references"]), 2)
        self.assertTrue(all("admiretheweb.com" in item["url"] for item in result["references"]))

    @patch("website_planning.requests.get")
    def test_reference_search_failure_is_nonfatal_and_actionable(self, get):
        import requests
        get.side_effect = requests.Timeout("test timeout")

        result = discover_admire_references("tree service")

        self.assertEqual(result["status"], "not_available")
        self.assertIn("manually", result["note"].lower())
        self.assertEqual(result["references"], [])

    def test_category_selects_distinct_layout_variants(self):
        self.assertEqual(choose_layout_variant("tree service"), "service-first")
        self.assertEqual(choose_layout_variant("restaurant"), "visual-first")
        self.assertEqual(choose_layout_variant("legal consulting"), "editorial")
        self.assertEqual(choose_layout_variant("local business"), "split-hero")

        strategy = build_seo_strategy({"business_type": "tree service"}, {})
        blueprint = build_design_blueprint({}, strategy, {"references": [], "status": "not_available"})
        self.assertEqual(blueprint["layout_variant"], "service-first")
        css = build_css_theme({}, blueprint["layout_variant"])
        self.assertIn(".layout-service-first .service-grid", css)

    def test_invalid_canonical_urls_are_discarded(self):
        strategy = build_seo_strategy(
            {"business_type": "tree service"},
            {"seo": {"canonical_url": "https:invalid.example/path"}},
        )
        self.assertIsNone(strategy["canonical_url"])

class SEOPlanningTests(unittest.TestCase):
    def test_strategy_uses_business_facts_and_labels_keyword_ideas(self):
        business = {
            "business_name": "Example Tree Care",
            "business_type": "tree service",
            "city": "Dallas, TX",
            "services": [{"name": "Tree trimming"}],
        }
        strategy = build_seo_strategy(business, {})
        self.assertIn("tree service", strategy["primary_keyword"].lower())
        self.assertIn("Dallas, TX", strategy["primary_keyword"])
        self.assertIn("Tree trimming", strategy["secondary_keyword_ideas"])
        self.assertIn("No search-volume", strategy["keyword_research_note"])
        self.assertIsNone(strategy["canonical_url"])

    def test_generated_html_has_seo_metadata_and_local_business_jsonld(self):
        business = {
            "business_name": "Example Tree Care",
            "business_type": "tree service",
            "city": "Dallas, TX",
            "phone": "555-0100",
            "address": "1 Main St, Dallas, TX",
        }
        strategy = build_seo_strategy(business, {})
        html = build_html(
            business,
            {
                "meta_title": "Example Tree Care | Tree Service",
                "meta_description": "Learn about tree care services in Dallas, TX.",
                "headline": "Tree Service in Dallas",
                "subheadline": "Learn about available tree care services.",
            },
            strategy,
        )
        self.assertIn('<meta name="description"', html)
        self.assertIn('property="og:title"', html)
        self.assertIn('type="application/ld+json"', html)
        report = validate_seo_html(html, business, strategy)
        self.assertEqual(report["status"], "PASS", report)

    def test_canonical_link_is_well_formed_when_configured(self):
        business = {
            "business_name": "Example Tree Care",
            "business_type": "tree service",
            "city": "Dallas, TX",
        }
        strategy = build_seo_strategy(
            business,
            {"seo": {"canonical_url": "https://example.com/tree-care"}},
        )
        html = build_html(business, {}, strategy)
        self.assertIn(
            '<link rel="canonical" href="https://example.com/tree-care">',
            html,
        )

    def test_empty_services_fallback_renders_category(self):
        html = build_html(
            {"business_name": "Example Tree Care", "business_type": "tree service"},
            {"services": []},
        )
        self.assertIn("<h3>\n                Tree Service\n            </h3>", html)
        self.assertNotIn("{escape(str(business_type_title))}", html)

    def test_non_http_business_website_is_not_rendered_as_link(self):
        html = build_html(
            {
                "business_name": "Example Tree Care",
                "business_type": "tree service",
                "website": "javascript:alert(1)",
            },
            {},
        )
        self.assertNotIn('href="javascript:alert(1)"', html)


    def test_design_tokens_are_sanitized_before_becoming_css(self):
        css = build_css_theme({
            "background": "#112233",
            "accent": "red; body { display:none }",
            "font_family": "expression(alert(1))",
            "radius": "999px",
        })
        self.assertIn("--bg: #112233;", css)
        self.assertNotIn("display:none", css)
        self.assertNotIn("expression", css)
        self.assertNotIn("999px", css)

    def test_seo_validator_flags_missing_alt_and_multiple_h1s(self):
        html = """<!doctype html><html><head><title>Example</title>
        <meta name="description" content="A useful description.">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        </head><body><h1>One</h1><h1>Two</h1><img src="tree.jpg">
        <script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"Example"}</script>
        </body></html>"""
        report = validate_seo_html(html, {"business_name": "Example"}, {})
        self.assertIn("Expected exactly one H1; found 2", report["issues"])
        self.assertTrue(any("alt attribute" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
