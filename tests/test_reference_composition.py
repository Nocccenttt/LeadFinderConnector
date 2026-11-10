import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from bs4 import BeautifulSoup
import reference_website_generator as generator
from reference_composition import validate_blueprint
from website_validator import validate


def stack(*slots):
    return {"type": "stack", "gap": 24, "children": [{"slot": slot} for slot in slots]}


def spec(image_first=False):
    hero_text = stack("eyebrow", "title", "text", "actions", "location")
    cells = [{"slot": "image"}, hero_text] if image_first else [hero_text, {"slot": "image"}]
    return {"reference_selection": {"website_url": "https://reference.example/"},
            "page_blueprint": {"version": 1, "sections": [
                {"key": "hero", "reference_section": 0, "adaptation": "Transfer the measured image/text split to the business introduction.",
                 "tone": "canvas", "width": "wide", "layout": {"type": "grid", "columns": [1.5, 1], "gap": 48, "children": cells}},
                {"key": "cta", "reference_section": 1, "adaptation": "Transfer the compact closing contact block to the business contact details.",
                 "tone": "brand", "width": "content", "layout": stack("eyebrow", "title", "text", "actions")},
            ]}}


def source():
    return {"website_url": "https://reference.example/", "rendered_desktop": {
        "status": "measured", "body": {"background": "#FFFBF4", "color": "#333333"},
        "sections": [{"padding": "64px 0px 96px"}, {"padding": "40px"}]}}


def content(design):
    return {"headline": "A specific approved headline", "subheadline": "Keep this approved introduction.",
            "about": "Approved business details.", "cta_title": "Talk to the business", "cta_text": "Call to discuss your needs.",
            "design_spec": design, "reference_research": [source()]}


class CompositionTests(unittest.TestCase):
    def test_dedicated_architecture_request_uses_selected_reference_and_corrects_invalid_output(self):
        client = Mock()
        invalid = spec()["page_blueprint"]
        invalid["sections"][0]["reference_section"] = 99
        def response(blueprint):
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"page_blueprint": blueprint})))])
        client.chat.completions.create.side_effect = [response(invalid), response(spec()["page_blueprint"])]
        with patch.object(generator, "log_usage"):
            result = generator.generate_composition(client, spec(), source(), content(spec()), {"business_name": "Example"})
        self.assertEqual(result, spec()["page_blueprint"])
        payload = client.chat.completions.create.call_args.kwargs
        self.assertEqual(json.loads(payload["messages"][1]["content"])["selected_reference"], "https://reference.example/")
        self.assertIn("JSON", payload["messages"][0]["content"])
        self.assertIn("Validation failed", payload["messages"][-1]["content"])

    def test_page_order_and_navigation_follow_only_the_blueprint_sections(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(generator, "download_stock_image", return_value="photo.jpg"):
            html = generator.build_html({"business_name": "Example", "phone": "5551234567"}, content(spec()), "care", Path(temp))
        page = BeautifulSoup(html, "html.parser")
        self.assertEqual([s["data-section"] for s in page.select("main>section")], ["hero", "cta"])
        self.assertEqual(page.select_one("h1").text, "A specific approved headline")
        self.assertIn("Keep this approved introduction.", page.get_text())
        self.assertNotIn("Protect the property", page.get_text())
        self.assertEqual([a["href"] for a in page.select("nav a")], ["#contact"])
        self.assertEqual(len(page.select("h1")), 1)

    def test_design_only_generation_preserves_content_and_exports_architecture(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "business.json").write_text('{"business_name":"Example","phone":"5551234567"}')
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}")
            previous = content(spec())
            (folder / "GENERATED_COPY.json").write_text(json.dumps(previous))
            fresh = content(spec(True))
            fresh["headline"] = "Discard this replacement headline"
            with patch.object(generator, "generate_copy", return_value=fresh), patch.object(generator, "download_stock_image", return_value="photo.jpg"):
                website = generator.generate_website(handoff, preserve_content=True)
            page = BeautifulSoup((website / "index.html").read_text(), "html.parser")
            self.assertEqual(page.h1.text, previous["headline"])
            self.assertIn(previous["subheadline"], page.get_text())
            self.assertEqual(page.select_one('[data-section="hero"] .rc-grid>div').select_one("img")["src"], "images/photo.jpg")
            report = json.loads((folder / "REFERENCE_IMPLEMENTATION.json").read_text())
            self.assertEqual(report["architecture_source"], "reference-mapped composition tree")
            self.assertFalse(report["uniqueness_verified"])
            self.assertEqual(json.loads((website / "design_spec.json").read_text())["section_order"], ["hero", "cta"])
            self.assertEqual(json.loads(validate(folder).read_text())["checks"]["composition"]["status"], "PASS")
            html = (website / "index.html").read_text()
            (website / "index.html").write_text(html.replace('data-reference-section="0"', 'data-reference-section="99"'))
            self.assertEqual(json.loads(validate(folder).read_text())["checks"]["composition"]["status"], "NEEDS REVIEW")

    def test_missing_or_repeated_content_is_rejected_instead_of_silently_rendered(self):
        for children in [[{"slot": "title"}], [{"slot": "title"}, {"slot": "title"}]]:
            design = spec()
            design["page_blueprint"]["sections"][0]["layout"] = {"type": "stack", "children": children}
            with self.assertRaises(ValueError):
                validate_blueprint(design, [source()])

    def test_unknown_reference_section_is_rejected(self):
        design = spec()
        design["page_blueprint"]["sections"][0]["reference_section"] = 99
        with self.assertRaises(ValueError):
            validate_blueprint(design, [source()])

    def test_arbitrary_copy_css_and_invalid_dimensions_are_rejected(self):
        for key, value in [("html", "<script>alert(1)</script>"), ("style", "position:fixed"), ("text", "Invented claim")]:
            design = spec()
            design["page_blueprint"]["sections"][0]["layout"][key] = value
            with self.assertRaises(ValueError):
                validate_blueprint(design, [source()])
        for value in [True, float("nan"), float("inf"), "1fr;display:none", -1, 999]:
            design = spec()
            design["page_blueprint"]["sections"][0]["layout"]["columns"][0] = value
            with self.assertRaises(ValueError):
                validate_blueprint(design, [source()])

    def test_overlay_rejects_invalid_children(self):
        design = spec()
        design["page_blueprint"]["sections"][0]["layout"] = {"type": "overlay", "children": [{"slot": "image"}, "invalid"]}
        with self.assertRaises(ValueError):
            validate_blueprint(design, [source()])

    def test_collections_keep_business_items_without_repeated_template_numbering(self):
        design = spec()
        design["page_blueprint"]["sections"].insert(1, {"key": "benefits", "reference_section": 1,
            "adaptation": "Adapt the reference's editorial list into useful customer information.",
            "tone": "canvas", "width": "wide", "layout": {"type": "grid", "columns": [1, 2], "children": [
                stack("title"), {"slot": "items", "columns": 1, "treatment": "rules", "numbered": False}]}})
        data = content(design)
        data["benefits"] = [{"title": "Ask a question", "text": "Discuss the options."}, {"title": "Plan ahead", "text": "Confirm availability."}]
        with tempfile.TemporaryDirectory() as temp, patch.object(generator, "download_stock_image", return_value="photo.jpg"):
            page = BeautifulSoup(generator.build_html({"business_name": "Example"}, data, "care", Path(temp)), "html.parser")
        section = page.select_one('[data-section="benefits"]')
        self.assertEqual([h.text for h in section.select("h3")], ["Ask a question", "Plan ahead"])
        self.assertNotIn("01", section.get_text())
        self.assertIn("Confirm availability.", section.get_text())


if __name__ == "__main__":
    unittest.main()
