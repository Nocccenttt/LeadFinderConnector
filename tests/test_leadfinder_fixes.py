"""Regression tests for LeadFinder's scrape-to-landing-page path."""

import unittest
from unittest.mock import Mock, patch

from deepseek_website_generator import build_html
from seo_lead_finder_prospecting_batch import google_places_search


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


if __name__ == "__main__":
    unittest.main()
