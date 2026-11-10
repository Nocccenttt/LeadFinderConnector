import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design_renderer import CHOICES, render_choices, layout_css, implementation_report
import reference_website_generator as generator
from website_planning import discover_admire_references


class ExecutableDesignTests(unittest.TestCase):
    def test_researched_tokens_do_not_claim_full_design_transfer_or_uniqueness(self):
        report = implementation_report({"reference_build_plan": {"status": "grounded"},
            "composition": {"about": "minimal", "services": "editorial"}})
        self.assertEqual(report["reference_transfer_status"], "partial")
        self.assertFalse(report["uniqueness_verified"])
        self.assertFalse(report["composition_coverage"]["about"]["changes_structure"])
        self.assertTrue(report["composition_coverage"]["services"]["changes_structure"])

    def test_full_width_split_does_not_become_background_overlay(self):
        result = render_choices({"hero_style": "Full-width split hero with a pet photo"})
        self.assertEqual(result["hero"], "split")

    def test_explicit_layout_rejects_descriptive_unrenderable_values(self):
        choices = {key: values[0] for key, values in CHOICES.items()}
        choices["hero"] = "large image on the right"
        with self.assertRaisesRegex(ValueError, "hero"):
            render_choices({"render_layout": choices})

    def test_split_and_centered_media_produce_different_html_structures(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(generator, "download_stock_image", return_value="photo.jpg"):
            choices = {key: values[0] for key, values in CHOICES.items()}
            copy = {"design_spec": {"render_layout": choices}}
            split = generator.build_html({"business_name": "Example"}, copy, "pet grooming", Path(temp))
            choices["hero"] = "centered-media"
            centered = generator.build_html({"business_name": "Example"}, copy, "pet grooming", Path(temp))
        self.assertIn('class="hero hero-split"', split)
        self.assertNotIn('class="hero hero-full-bleed"', split)
        self.assertIn('class="hero hero-centered-media"', centered)
        self.assertIn('class="hero-wide-image"', centered)
        self.assertNotIn('class="hero-wide-image"', split)

    def test_design_revision_keeps_existing_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "business.json").write_text(json.dumps({"business_name": "Example", "business_type": "pet grooming"}))
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}")
            previous = {"headline": "Keep this headline", "about": "Keep this paragraph", "seo": {"meta_description": "Keep this description"}}
            (folder / "GENERATED_COPY.json").write_text(json.dumps(previous))
            fresh = {"headline": "Discard this rewrite", "reference_research": [],
                     "design_spec": {"render_layout": {key: values[0] for key, values in CHOICES.items()}}}
            with patch.object(generator, "generate_copy", return_value=fresh), patch.object(generator, "download_stock_image", return_value="photo.jpg"):
                generator.generate_website(handoff, preserve_content=True)
            actual = json.loads((folder / "GENERATED_COPY.json").read_text())
            for key, value in previous.items():
                self.assertEqual(actual[key], value)
            self.assertTrue(json.loads((folder / "RENDERED_DESIGN.json").read_text())["content_preserved"])

    def test_adjacent_search_is_attempted_before_generic_gallery(self):
        from unittest.mock import Mock
        search = Mock(text="<html></html>")
        empty = Mock()
        empty.json.return_value = []
        related = Mock()
        related.json.return_value = [{"title": "Care Design", "url": "https://api.admiretheweb.com/inspiration/care-design/"}]
        with patch("website_planning.requests.get", side_effect=[search, empty, related]) as get:
            result = discover_admire_references("pet grooming", broaden=True)
        self.assertEqual(result["discovery_method"], "related_search_api")
        self.assertEqual(get.call_args.kwargs["params"]["search"], "care")
        self.assertIn("not verified matches", result["note"])


if __name__ == "__main__":
    unittest.main()
