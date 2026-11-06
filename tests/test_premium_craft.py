import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

import reference_website_generator as generator
from test_reference_composition import spec, source, content, stack


def expanded_copy():
    data = content(spec())
    data.update(feature_title="A whole personality.", feature_text="Share the little things that matter to your pet.",
                guide_title="Before your next visit", guide_intro="A few useful things to discuss.",
                guide_topics=[{"title":"The coat", "text":"Describe the finish you have in mind.", "prompt":"Ask what is included."}])
    data["design_spec"]["page_blueprint"]["sections"].insert(1, {
        "key":"feature", "reference_section":1,"adaptation":"Transfer the measured source's contrasting editorial image and text block.",
        "tone":"brand","width":"wide","layout":{"type":"grid","columns":[1.2,.8],"children":[stack("title","text"),{"slot":"image"}]}})
    data["design_spec"]["page_blueprint"]["sections"].insert(2, {
        "key":"guide", "reference_section":1,"adaptation":"Transfer the measured editorial list into the customer's planning guidance.",
        "tone":"canvas","width":"wide","layout":{"type":"grid","columns":[1,1.5],"children":[stack("title","text"),{"slot":"items","columns":1,"treatment":"rules"}]}})
    return data


def photo(query, output, name):
    folder = Path(output)
    folder.mkdir(exist_ok=True)
    filename = name + ".png"
    (folder/filename).write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aNZkAAAAASUVORK5CYII="))
    return filename


class GroundedCopyTests(unittest.TestCase):
    def test_cached_design_revision_keeps_copy_and_uses_only_architecture_request(self):
        data = expanded_copy()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/'business.json').write_text('{"business_name":"Example","phone":"5551234567"}')
            handoff=folder/'AI_HANDOFF.json'
            handoff.write_text('{"reuse_reference_research":true}')
            (folder/'GENERATED_COPY.json').write_text(json.dumps(data))
            research=folder/'REFERENCE_RESEARCH'
            research.mkdir()
            (research/'CANDIDATES.json').write_text(json.dumps([source()]))
            client=Mock()
            client.chat.completions.create.return_value=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10,completion_tokens=10,total_tokens=20),choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'page_blueprint':data['design_spec']['page_blueprint']})))])
            with patch.object(generator,'OpenAI',return_value=client),patch.object(generator,'download_stock_image',side_effect=photo),patch.object(generator,'log_usage'):
                website=generator.generate_website(handoff,preserve_content=True)
            actual=json.loads((folder/'GENERATED_COPY.json').read_text())
            self.assertEqual(actual['headline'],data['headline'])
            self.assertEqual(actual['guide_topics'],data['guide_topics'])
            self.assertEqual(client.chat.completions.create.call_count,1)
            self.assertIn(data['headline'],(website/'index.html').read_text())

    def test_general_marketing_copy_survives_sparse_business_generation(self):
        data = expanded_copy()
        data["headline"] = "A fresh look. Same best friend."
        result = generator.guard_sparse_business_copy(data, {"business_name":"Example","business_type":"pet grooming"}, {}, preserve_general_copy=True)
        self.assertEqual(result["headline"], data["headline"])
        self.assertEqual(result["guide_topics"], data["guide_topics"])
        self.assertEqual(result["feature_text"], data["feature_text"])
        self.assertEqual(result["services"], [])

    def test_unsupported_prices_credentials_and_company_offerings_fail(self):
        for assertion in ("We offer stump grinding.", "Certified experts since 1995.", "Visits start at $30."):
            data = expanded_copy()
            data["subheadline"] = assertion
            with self.assertRaises(ValueError):
                generator.guard_sparse_business_copy(data, {"business_name":"Example"}, {}, preserve_general_copy=True)


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1", "Enable rendered craft checks")
class PremiumBrowserTests(unittest.TestCase):
    def test_generated_site_has_readable_font_guidance_and_accessible_motion(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/'business.json').write_text('{"business_name":"Example","business_type":"pet grooming","phone":"5551234567"}')
            handoff = folder/'AI_HANDOFF.json'
            handoff.write_text('{}')
            with patch.object(generator,'generate_copy',return_value=expanded_copy()), patch.object(generator,'download_stock_image',side_effect=photo):
                website = generator.generate_website(handoff)
            self.assertTrue((website/'fonts/Geist-OFL.txt').is_file())
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch()
                try:
                    page = browser.new_page(viewport={"width":1440,"height":1000},reduced_motion='reduce')
                    page.goto((website/'index.html').as_uri())
                    page.evaluate('document.fonts.ready')
                    self.assertIn('Craft Sans', page.locator('body').evaluate('(el)=>getComputedStyle(el).fontFamily'))
                    self.assertIn('A whole personality.',page.locator('main').inner_text())
                    self.assertIn('Describe the finish',page.locator('[data-section="guide"]').inner_text())
                    page.keyboard.press('Tab')
                    self.assertEqual(page.locator('.skip-link').evaluate('(el)=>el===document.activeElement'),True)
                    self.assertEqual(page.locator('.skip-link').evaluate('(el)=>getComputedStyle(el).transform'),'none')
                    page.set_viewport_size({"width":390,"height":844})
                    self.assertEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                    page.locator('.menu-toggle').click()
                    self.assertEqual(page.locator('.menu-toggle').get_attribute('aria-expanded'),'true')
                    page.keyboard.press('Escape')
                    self.assertEqual(page.locator('.menu-toggle').get_attribute('aria-expanded'),'false')
                    self.assertEqual(page.evaluate('document.getAnimations().filter(a=>a.playState==="running").length'),0)
                finally:
                    browser.close()
