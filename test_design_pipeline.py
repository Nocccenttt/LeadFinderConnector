"""Offline regressions for discovery, grounded content and opposing render specs.
Run: python -m unittest test_design_pipeline
Live checkpoint commands are documented in DESIGN_PIPELINE.md.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_saved_content_survives_reruns_and_cannot_be_reduced_to_contacts(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            handoff = folder / "AI_HANDOFF.json"
            handoff.write_text("{}", encoding="utf-8")
            (folder / "business.json").write_text(json.dumps(self.business), encoding="utf-8")
            (folder / "reference_analysis.json").write_text(json.dumps({"schema_version": 2, "reference": {"url": "https://example.com"}}), encoding="utf-8")
            spec = copy.deepcopy(generator.DEFAULT_DESIGN_SPEC)
            (folder / "design_spec.json").write_text(json.dumps(spec), encoding="utf-8")
            content = generator.verified_business_content(self.business, {}, {})
            content["services"] = [{"name": "Tree removal", "description": "Preserve this supplied service description in full."}]
            content["research_sources"] = ["https://example.com/services"]
            content_file = folder / "supplied_content.json"
            content_file.write_text(json.dumps(content), encoding="utf-8")
            with patch.object(generator, "generate_business_content", side_effect=AssertionError("Must not replace saved copy")), patch.object(generator, "load_or_research_business", side_effect=AssertionError("Must not fetch instead of using supplied copy")):
                output = generator.generate_website(handoff, content_file=content_file)
                original = (output / "index.html").read_bytes()
                self.assertIn(b"Preserve this supplied service description in full.", original)
                generator.generate_website(handoff)
                self.assertEqual((output / "index.html").read_bytes(), original)
                with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                    generator.generate_website(handoff, handoff_only=True)
                self.assertEqual((output / "index.html").read_bytes(), original)
                spec["sections"] = [spec["sections"][0], spec["sections"][-1]]
                (folder / "design_spec.json").write_text(json.dumps(spec), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "drop saved content"):
                    generator.generate_website(handoff, content_file=content_file)
                self.assertEqual((output / "index.html").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
