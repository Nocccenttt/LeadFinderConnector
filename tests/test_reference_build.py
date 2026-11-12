import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reference_build import reference_build_plan, reference_build_css
from design_renderer import CHOICES
import reference_website_generator as generator


def candidate():
    return {"website_url": "https://care.example/", "hub_url": "https://admiretheweb.com/inspiration/care/",
            "rendered_desktop": {"status": "measured", "viewport": {"width": 1440, "height": 1000},
                "body": {"font": "Proprietary Serif, Georgia, serif", "size": "14px", "lineHeight": "24px",
                         "color": "rgb(51, 51, 51)", "background": "rgb(255, 251, 244)"},
                "headings": [{"tag": "H1", "font": "Proprietary Display, Georgia, serif", "size": "92px", "weight": "500",
                              "rect": {"x": 120, "y": 220, "width": 600, "height": 100}}],
                "images": [{"rect": {"x": 720, "y": 90, "width": 720, "height": 540}}],
                "sections": [{"padding": "84px 0px"}], "controls": [{"radius": "0px"}]}}


class ReferenceBuildTests(unittest.TestCase):
    def test_measurements_determine_build_proportions_with_readability_floor(self):
        plan = reference_build_plan({"reference_selection": {"website_url": "https://care.example/"}}, [candidate()])
        self.assertEqual(plan["suggested_hero"], "split")
        self.assertEqual(plan["tokens"]["container_px"], 1200)
        self.assertEqual(plan["tokens"]["heading_px"], 92)
        self.assertEqual(plan["tokens"]["body_px"], 17)
        self.assertEqual(plan["tokens"]["section_space_px"], 84)
        self.assertEqual(plan["tokens"]["image_ratio"], 1.333)
        self.assertEqual(plan["tokens"]["heading_family"], "serif")

    def test_missing_render_does_not_claim_reference_grounding(self):
        item = candidate()
        item["rendered_desktop"] = {"status": "unavailable"}
        plan = reference_build_plan({"reference_selection": {"website_url": item["website_url"]}}, [item])
        self.assertEqual(plan["status"], "unmeasured")
        self.assertEqual(reference_build_css(plan), "")

    def test_distinct_reference_geometry_changes_image_side_and_column_proportions(self):
        right = candidate()
        left = candidate()
        left["rendered_desktop"]["headings"][0]["rect"] = {"x": 850, "y": 220, "width": 400, "height": 100}
        left["rendered_desktop"]["images"][0]["rect"] = {"x": 120, "y": 90, "width": 650, "height": 540}
        spec = {"reference_selection": {"website_url": right["website_url"]}}
        right_plan = reference_build_plan(spec, [right])
        left_plan = reference_build_plan(spec, [left])
        self.assertEqual(left_plan["suggested_hero"], "split")
        self.assertEqual(left_plan["tokens"]["hero_image_side"], "left")
        self.assertEqual(left_plan["tokens"]["hero_columns"], [1.625, 1])
        self.assertNotEqual(reference_build_css(right_plan), reference_build_css(left_plan))

    def test_monospace_reference_is_not_replaced_with_generic_sans(self):
        item = candidate()
        item["rendered_desktop"]["headings"][0]["font"] = "Source Code Pro, monospace"
        plan = reference_build_plan({"reference_selection": {"website_url": item["website_url"]}}, [item])
        self.assertEqual(plan["tokens"]["heading_family"], "monospace")
        self.assertIn("--font-heading:'Courier New', monospace", reference_build_css(plan))

    def test_full_width_image_overlapping_heading_is_not_forced_into_split(self):
        item = candidate()
        item["rendered_desktop"]["images"][0]["rect"] = {"x": 0, "y": 90, "width": 1440, "height": 700}
        plan = reference_build_plan({"reference_selection": {"website_url": item["website_url"]}}, [item])
        self.assertEqual(plan["suggested_hero"], "full-bleed")

    def test_render_boundary_limits_numeric_values_and_never_embeds_source_fonts(self):
        plan = reference_build_plan({"reference_selection": {"website_url": "https://care.example/"}}, [candidate()])
        plan["tokens"]["heading_px"] = "999999px;body{display:none}"
        css = reference_build_css(plan)
        self.assertNotIn("display:none", css)
        self.assertNotIn("Proprietary", css)
        self.assertIn("96px", css)
        self.assertIn("font-display:swap", css)

    def test_generation_installs_licensed_fonts_and_saves_implemented_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "business.json").write_text(json.dumps({"business_name": "Example", "business_type": "pet grooming"}))
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}")
            spec = {"reference_selection": {"website_url": "https://care.example/"},
                    "render_layout": {key: values[0] for key, values in CHOICES.items()}}
            with patch.object(generator, "generate_copy", return_value={"design_spec": spec, "reference_research": [candidate()]}), patch.object(
                generator, "download_stock_image", return_value="photo.jpg"
            ):
                website = generator.generate_website(handoff)
            plan = json.loads((folder / "REFERENCE_BUILD_PLAN.json").read_text())
            self.assertEqual(plan["status"], "grounded")
            self.assertTrue((website / "fonts" / "LibreCaslonDisplay-Regular.ttf").is_file())
            self.assertTrue((website / "fonts" / "LibreCaslonDisplay-OFL.txt").is_file())
            css = (website / "styles.css").read_text()
            self.assertIn("--max:1200px", css)
            self.assertIn("--section-space:84px", css)
