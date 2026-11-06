"""Run with RUN_BROWSER_TESTS=1 after installing Playwright Chromium."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import reference_website_generator as generator
from reference_composition import blueprint_css
from test_reference_composition import spec, content


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1", "Enable RUN_BROWSER_TESTS for rendered composition checks")
class RenderedCompositionTests(unittest.TestCase):
    def test_lower_page_collection_obeys_columns_and_mobile_reading_order(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                texts = []
                for columns in (3, 1):
                    design = spec()
                    design["page_blueprint"]["sections"].insert(1, {"key": "benefits", "reference_section": 1,
                        "adaptation": "Transfer the source's content grouping into the customer information block.",
                        "tone": "canvas", "width": "wide", "layout": {"type": "stack", "children": [
                            {"slot": "title"}, {"slot": "items", "columns": columns, "treatment": "rules"}]}})
                    data = content(design)
                    data["benefits"] = [{"title": title, "text": "Approved customer information."} for title in ("Ask", "Plan", "Confirm")]
                    with tempfile.TemporaryDirectory() as temp, patch.object(generator, "download_stock_image", return_value="photo.jpg"):
                        html = generator.build_html({"business_name": "Example"}, data, "care", Path(temp))
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.set_content(html)
                    page.add_style_tag(content=generator.CSS + generator.build_design_css(design) + blueprint_css(design))
                    xs = page.locator('[data-section="benefits"] h3').evaluate_all('(els)=>els.map(el=>Math.round(el.getBoundingClientRect().x))')
                    self.assertEqual(len(set(xs)), columns)
                    extent = page.locator('[data-section="benefits"]').evaluate('(el)=>({items:el.querySelector(".rc-items").getBoundingClientRect().width,shell:el.querySelector(".rc-shell").getBoundingClientRect().width})')
                    self.assertGreater(extent["items"], extent["shell"] * .95)
                    texts.append(page.locator('[data-section="benefits"]').inner_text())
                    page.set_viewport_size({"width": 390, "height": 844})
                    self.assertEqual(page.locator('[data-section="benefits"] h3').all_text_contents(), ["Ask", "Plan", "Confirm"])
                    self.assertEqual(len(set(page.locator('[data-section="benefits"] h3').evaluate_all('(els)=>els.map(el=>el.getBoundingClientRect().x)'))), 1)
                self.assertEqual(texts[0], texts[1])
            finally:
                browser.close()

    def test_research_excludes_hidden_and_navigation_images_from_section_geometry(self):
        from playwright.sync_api import sync_playwright
        from reference_visuals import MEASURE_DESIGN
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_content('<header><img alt="menu" style="width:400px;height:400px"></header><main><section><h1>Actual section</h1><img alt="content" style="width:600px;height:300px"><div style="opacity:0"><img alt="hidden" style="width:400px;height:300px"></div><img alt="other slide" style="position:absolute;left:1440px;width:1000px;height:600px"></section></main>')
                observed = page.evaluate(MEASURE_DESIGN)
                self.assertEqual([image["alt"] for image in observed["images"]], ["content"])
                self.assertEqual(len(observed["sections"][0]["section_layouts"]["images"]), 1)
            finally:
                browser.close()

    def test_same_content_obeys_distinct_compositions_and_stacks_without_overflow(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                states = []
                for image_first in (False, True):
                    design = spec(image_first)
                    with tempfile.TemporaryDirectory() as temp, patch.object(generator, "download_stock_image", return_value="photo.jpg"):
                        html = generator.build_html({"business_name": "Example", "phone": "5551234567"}, content(design), "care", Path(temp))
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.set_content(html)
                    page.add_style_tag(content=generator.CSS + generator.build_design_css(design) + blueprint_css(design))
                    state = page.evaluate('''() => {
                        const hero=document.querySelector('[data-section="hero"]');
                        const image=hero.querySelector('img').getBoundingClientRect();
                        const title=hero.querySelector('h1').getBoundingClientRect();
                        return {imageX:image.x,titleX:title.x,titleWidth:title.width,text:hero.innerText};
                    }''')
                    self.assertEqual(state["imageX"] < state["titleX"], image_first)
                    self.assertGreater(state["titleWidth"], 300)
                    states.append(state)
                    page.set_viewport_size({"width": 390, "height": 844})
                    mobile = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,tracks:getComputedStyle(document.querySelector(".rc-grid")).gridTemplateColumns})')
                    self.assertEqual(mobile["width"], mobile["scroll"])
                    self.assertEqual(len(mobile["tracks"].split()), 1)
                    self.assertEqual(page.locator("h1").count(), 1)
                self.assertEqual(states[0]["text"], states[1]["text"])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
