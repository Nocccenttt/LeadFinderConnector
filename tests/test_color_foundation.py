import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from color_foundation import build_color_foundation, contrast, foundation_css, mix, normalize_color
from website_validator import validate
import reference_website_generator as generator


def source():
    return {"website_url": "https://reference.example/", "rendered_desktop": {"status": "measured",
            "body": {"background": "rgb(255, 251, 244)", "color": "rgb(51, 51, 51)"},
            "sections": [{"background": "rgb(71, 31, 30)", "color": "rgb(255, 251, 244)",
                          "rect": {"width": 1440, "height": 720}}]}}


def design():
    return {"reference_selection": {"website_url": "https://reference.example/"},
            "design_system": {"palette": {"primary": "#00FF00", "accent": "#FF00FF"}}}


class ColorFoundationTests(unittest.TestCase):
    def test_measured_reference_is_the_basis_instead_of_ai_palette(self):
        result = build_color_foundation({}, {}, design(), [source()])
        self.assertEqual(result["source"], "measured_reference")
        self.assertEqual(result["primitives"], {"brand_anchor": "#471F1E", "canvas_anchor": "#FFFBF4", "text_anchor": "#333333"})
        self.assertEqual(result["palette"]["primary"], "#471F1E")
        self.assertIn("sections[0]", result["provenance"]["brand_anchor"])
        self.assertNotIn("#00FF00", result["palette"].values())

    def test_explicit_brand_takes_precedence_and_keeps_anchor_unchanged(self):
        result = build_color_foundation({"brand": {"colors": {"primary": "#2266FF"}}}, {}, design(), [source()])
        self.assertEqual(result["source"], "explicit_brand")
        self.assertEqual(result["primitives"]["brand_anchor"], "#2266FF")
        self.assertEqual(result["provenance"]["brand_anchor"], "business.brand.colors.primary")
        self.assertEqual(result["contrast"]["status"], "PASS")

    def test_light_brand_gets_accessible_semantic_tones_without_replacing_anchor(self):
        result = build_color_foundation({"brand_colors": {"primary": "#FFFF00", "background": "#FFFFFF", "text": "#FFFFFF"}}, {}, {}, [])
        self.assertEqual(result["primitives"]["brand_anchor"], "#FFFF00")
        self.assertNotEqual(result["tokens"]["action"]["primary"], "#FFFF00")
        self.assertNotEqual(result["tokens"]["text"]["primary"], "#FFFFFF")
        self.assertTrue(all(item["pass"] for item in result["contrast"]["checks"]))

    def test_all_normal_and_interaction_pairs_pass_without_threshold_rounding(self):
        result = build_color_foundation({}, {}, design(), [source()])
        for item in result["contrast"]["checks"]:
            self.assertGreaterEqual(contrast(item["foreground"], item["background"]), item["minimum"], item["role"])
        self.assertEqual(contrast("#000000", "#FFFFFF"), 21)
        self.assertLess(contrast("#777777", "#FFFFFF"), 4.5)

    def test_transparency_and_css_injection_are_not_foundation_colors(self):
        self.assertIsNone(normalize_color("rgba(71,31,30,0.4)"))
        self.assertIsNone(normalize_color("#FFFFFF;body{display:none}"))
        self.assertEqual(normalize_color("#abc"), "#AABBCC")
        with self.assertRaises(ValueError):
            build_color_foundation({"brand_colors": {"primary": "red;display:none"}}, {}, {}, [])

    def test_oklab_round_trip_preserves_anchor_colors(self):
        for color in ("#000000", "#FFFFFF", "#471F1E", "#FFFBF4", "#2266FF"):
            self.assertEqual(mix(color, color, .5), color)

    def test_missing_sources_are_reported_instead_of_labeled_as_grounded(self):
        result = build_color_foundation({}, {}, design(), [])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(foundation_css(result), "")

    def test_generator_consumes_foundation_and_exports_semantic_tokens(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "business.json").write_text('{"business_name":"Example"}')
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}")
            with patch.object(generator, "generate_copy", return_value={"design_spec": design(), "reference_research": [source()]}), patch.object(
                generator, "download_stock_image", return_value="photo.jpg"
            ):
                website = generator.generate_website(handoff)
            css = (website / "styles.css").read_text()
            self.assertIn("--color-action-primary: #471F1E", css)
            self.assertNotIn("#00FF00", css)
            self.assertTrue((website / "color-tokens.json").is_file())
            self.assertEqual(json.loads((folder / "COLOR_FOUNDATION.json").read_text())["contrast"]["status"], "PASS")

    def test_validator_recalculates_contrast_instead_of_trusting_saved_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "business.json").write_text('{"business_name":"Example"}')
            website = folder / "website"
            website.mkdir()
            for name, value in {"index.html": "<title>Example</title><h1>Example</h1>", "styles.css": "body{}", "script.js": "// script"}.items():
                (website / name).write_text(value)
            (folder / "COLOR_FOUNDATION.json").write_text(json.dumps({"status": "grounded", "contrast": {
                "status": "PASS", "checks": [{"foreground": "#FFFFFF", "background": "#FFFFFF", "minimum": 4.5, "pass": True}]}}))
            report = json.loads(validate(folder).read_text())
            self.assertEqual(report["checks"]["colors"]["status"], "NEEDS REVIEW")


if __name__ == "__main__":
    unittest.main()
