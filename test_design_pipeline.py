"""Offline regressions for discovery, grounded content and opposing render specs.
Run: python -m unittest test_design_pipeline
Live checkpoint commands are documented in DESIGN_PIPELINE.md.
"""
import copy
import unittest
from unittest.mock import patch

import deepseek_website_generator as generator


class DesignPipelineTests(unittest.TestCase):
    business = {"business_name": "Brown's Tree Service", "phone": "(919) 845-6222", "address": "5104 Yachtsman Ct, Raleigh, NC 27615, USA"}

    def test_v7_targets_submitted_link_and_filters_junk(self):
        html = '''<a href="https://cdn.usefathom.com/tracker.js">junk</a>
        <div class="c-item__image"><a href="https://raggededge.com">submitted</a></div>'''
        self.assertEqual(generator.extract_submitted_site(html), "https://raggededge.com")
        for url in ("https://schema.org", "https://www.admiretheweb.com/inspiration/test/", "https://sub.facebook.com", "https://example.com/assets/a", "https://example.com/logo.svg", "javascript:alert(1)", "https://user:password@example.com"):
            self.assertEqual(generator.clean_reference_url(url), "", url)
        self.assertEqual(generator.clean_reference_url("https://example.com/?a=1&amp;b=2"), "https://example.com/?a=1&b=2")

    def test_discovery_returns_four_unique_websites_from_entries(self):
        names = ("Ragged Edge", "North Design", "Geist Studio", "Special Projects")
        urls = ("https://raggededge.com", "https://northdesign.com", "https://geist.studio", "https://www.s-p.studio")
        hub = "".join(f'<article class="c-item"><a href="/inspiration/{i}/">{name}</a></article>' for i, name in enumerate(names))
        def fetch(url, **kwargs):
            if url == generator.ADMIRE_URL:
                return hub, url
            index = int(url.rstrip("/").rsplit("/", 1)[1])
            return f'<div class="c-item__title"><a href="{urls[index]}">Website</a></div>', url
        with patch.object(generator, "fetch_page", side_effect=fetch):
            candidates = generator.discover_reference_websites()
        self.assertEqual([item["url"] for item in candidates], list(urls))
        self.assertTrue(all("/inspiration/" in item["entry_url"] for item in candidates))

    def test_opposing_specs_change_style_composition_and_order(self):
        light = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
        dark = copy.deepcopy(light)
        dark["colors"].update(background="#101010", text="#FFFFFF", surface="#202020", accent="#FFFFFF", on_accent="#101010")
        dark["hero"]["layout"] = "split"
        dark["layout"]["composition"] = "asymmetric"
        dark["typography"]["heading_family"] = "mono"
        dark["spacing"]["section"] = 160
        dark["components"].update(cards="none", button="outline", radius=20)
        dark["sections"] = [dark["sections"][0], {"type": "local", "layout": "rows", "width": "full-bleed", "tone": "accent"}, dark["sections"][-1]]
        content = generator.verified_business_content(self.business, {}, {})
        first = generator.build_html(self.business, content, light)
        second = generator.build_html(self.business, content, dark)
        css = generator.css_for_design_spec(dark, {"background": "#FF0000"})
        self.assertIn('data-hero="editorial"', first)
        self.assertIn('data-hero="split"', second)
        self.assertIn('data-cards="none"', second)
        self.assertNotIn('id="about"', second)
        self.assertLess(second.index('id="local"'), second.index('id="contact"'))
        for token in ("--bg:#101010", "--section:160px", "--radius:20px", "'Courier New',monospace"):
            self.assertIn(token, css)
        self.assertNotIn("#FF0000", css)
        self.assertNotIn("__", css)

    def test_handoff_only_omits_invented_services_and_claims(self):
        content = generator.verified_business_content(self.business, {}, {})
        html = generator.build_html(self.business, content, generator.DEFAULT_DESIGN_SPEC)
        for section in ("services", "proof", "reviews", "faq", "process"):
            self.assertNotIn(f'id="{section}"', html)
        self.assertIn("(919) 845-6222", html)
        self.assertIn('href="tel:9198456222"', html)
        self.assertEqual(content["services"], [])
        self.assertEqual(content["proof_points"], [])
        self.assertTrue(content["content_gaps"])

    def test_unsafe_tokens_and_inaccessible_colors_are_rejected(self):
        for group, field, value in (("colors", "accent", "red; background:url(evil)"), ("spacing", "section", 99999), ("hero", "layout", "unbounded-html"), ("motion", "duration", float("nan"))):
            spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
            spec[group][field] = value
            with self.assertRaises(ValueError):
                generator.validate_design_spec(spec)
        spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
        spec["colors"]["text"] = "#FFFFFF"
        with self.assertRaises(ValueError):
            generator.css_for_design_spec(spec)
        spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
        spec["sections"][1]["layout"] = "overlap"
        with self.assertRaises(ValueError):
            generator.validate_design_spec(spec)

    def test_non_tree_business_without_images_renders_and_escapes_content(self):
        business = {"business_name": '<script>alert("x")</script>', "phone": "123", "address": "Raleigh, NC"}
        content = generator.verified_business_content(business, {}, {})
        html = generator.build_html(business, content)
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('type="application/ld+json"', html)
        self.assertNotIn('class="hero-image"', html)


if __name__ == "__main__":
    unittest.main()
