import unittest
from unittest.mock import Mock, patch

import requests
from website_planning import discover_admire_references, merge_design_references


class ReferenceTests(unittest.TestCase):
    @patch("website_planning.requests.get")
    def test_relative_heading_link_wins_over_empty_image_link(self, get):
        response = Mock()
        response.text = '''<article><a href="/inspiration/example/"><img alt="Example"></a>
        <h2><a href="/inspiration/example/">Example Studio</a></h2></article>'''
        get.return_value = response
        result = discover_admire_references("tree service")
        self.assertEqual(result["references"][0]["title"], "Example Studio")
        self.assertEqual(result["references"][0]["url"], "https://www.admiretheweb.com/inspiration/example/")
        self.assertIn("/search/tree%20service/", get.call_args.args[0])

    @patch("website_planning.requests.get")
    def test_api_fallback_uses_public_permalink_and_decodes_title(self, get):
        failed = Mock()
        failed.raise_for_status.side_effect = requests.HTTPError("404")
        api = Mock()
        api.json.return_value = [{"title": "Food &amp; Co", "url": "https://api.admiretheweb.com/inspiration/food/"}]
        get.side_effect = [failed, api]
        result = discover_admire_references("restaurant")
        self.assertEqual(result["discovery_method"], "search_api")
        self.assertEqual(result["references"][0]["url"], "https://admiretheweb.com/inspiration/food/")
        self.assertEqual(result["references"][0]["title"], "Food & Co")

    @patch("website_planning.requests.get")
    def test_empty_search_falls_back_to_clearly_labeled_gallery(self, get):
        search = Mock(text="<html></html>")
        api = Mock()
        api.json.return_value = []
        gallery = Mock(text='<article><h2><a href="/inspiration/food/">Food</a></h2></article>')
        get.side_effect = [search, api, gallery]
        result = discover_admire_references("restaurant")
        self.assertEqual(result["discovery_method"], "category_gallery")
        self.assertIn("not verified matches", result["note"])
        self.assertTrue(get.call_args.args[0].endswith("/category/food/"))

    @patch("website_planning.requests.get")
    def test_zero_limit_makes_no_requests(self, get):
        self.assertEqual(discover_admire_references("tree", limit=0)["references"], [])
        get.assert_not_called()

    def test_curated_references_are_sanitized_bounded_and_prioritized(self):
        result = merge_design_references({"status": "not_available", "references": [], "note": "Search offline."}, [
            {"url": "javascript:alert(1)"}, {"url": "https://name:password@example.com/"},
            {"url": "https://example.com/style#section", "title": "A" * 300, "excerpt": "B" * 500,
             "unexpected": "ignore"},
            "https://example.com/style", "https://example.com/other",
        ])
        self.assertEqual(result["status"], "found")
        self.assertEqual(len(result["references"]), 2)
        self.assertEqual(len(result["references"][0]["title"]), 160)
        self.assertEqual(len(result["references"][0]["excerpt"]), 300)
        self.assertNotIn("unexpected", result["references"][0])
        self.assertIn("not been fetched", result["note"])

    @patch("website_planning.requests.get")
    def test_lookalike_hosts_and_non_inspiration_api_results_are_rejected(self, get):
        search = Mock(text='<article><h2><a href="https://admiretheweb.com.attacker.invalid/fake">Fake</a></h2></article>')
        api = Mock()
        api.json.return_value = [{"title": "Article", "url": "https://api.admiretheweb.com/articles/other/"}]
        gallery = Mock(text="<html></html>")
        get.side_effect = [search, api, gallery]
        self.assertEqual(discover_admire_references("tree service")["references"], [])


if __name__ == "__main__":
    unittest.main()
