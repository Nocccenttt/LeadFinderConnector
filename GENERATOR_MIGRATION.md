# Active reference generator

The dashboard and batch pipeline now use `reference_website_generator.py`, ported from:

`../LeadFinder_Updated_Images/Lead_Finder_Deepseek/_archive/generator/deepseek_website_generator_PHASE2C3_FIXED7.py`

The old `deepseek_website_generator.py` command also delegates to the active generator. Its old Python rendering functions remain available for compatibility and regression coverage.

## What runs

1. Build an SEO strategy from business.json.
2. Discover Admire entries through the repaired search/API/gallery flow.
3. Extract actual submitted website URLs using the known c-item markup from the v7 extractor.
4. Fetch actual reference HTML and up to two linked stylesheets per candidate. Supply headings, text snapshots, frequent colors, font families, and grid/flex counts to DeepSeek. Public-address checks apply to each reference request and redirect.
5. Let DeepSeek select one researched website and return its analysis, design system, section order, composition, copy, and image queries.
6. Render the archived generator's photographic hero variants, palettes, section tones, composition choices, and responsive styles. Save the model's spec and researched candidates.
7. Download Pexels stock images locally. New image downloads save credit metadata. If the image API fails, the archived SVG placeholder fallback remains and is logged.
8. Run the existing quality checks, status handling, delivery metadata, and sales-package flow.

The current research also captures rendered desktop computed styles, geometry, and source screenshots. The text model receives measurements, not image vision input. Responsive behavior and motion are not independently verified on reference sites. See REFERENCE_DESIGN_UPDATE.md for the current layout contract and content-preserving revisions. Stock photographs do not depict the prospect's work.

## Repairs made during migration

- Corrected mismatched candidate fields (`site_url` versus `website_url`) and populated actual-site research.
- Added the archive's missing JavaScript bundle, including the mobile menu and progressive reveal behavior.
- Increased the model output budget to fit the fuller JSON schema.
- Normalized descriptive composition choices to the renderer's supported labels.
- Ensured one hero is present even when the model omits it from section_order.
- Fixed `sans-serif` being incorrectly interpreted as a request for serif typography.
- Retained URL sanitation, safe JSON-LD, configured canonicals, and saved SEO reports.
- Changed claim checks to inspect visible text, so inline CSS hex values do not trigger false '#1' claims.
- Replaced archive-specific tree-care boilerplate with neutral planning guidance.
- For leads without verified services, apply factual contact copy instead of publishing invented services or operational promises. The AI-selected visual design remains intact.

## Configuration and outputs

`DEEPSEEK_API_KEY` powers generation. `PEXELS_API_KEY` powers stock-image search. `GOOGLE_MAPS_API_KEY` is needed only for new prospect discovery.

Direct generation:

```powershell
python reference_website_generator.py "path\to\client\AI_HANDOFF.json"
```

Full generation, validation, and delivery flow:

```powershell
python pipeline_runner.py "path\to\client"
```

Per client: SEO_STRATEGY.json, DESIGN_REFERENCES.json, DESIGN_BLUEPRINT.json, GENERATED_COPY.json, SEO_QA_REPORT.json, quality_report.json, and website assets including images and design_spec.json. Preview pages intentionally retain `noindex`.

## Verification

52 regression tests pass. The live Brown's Tree Service run researched four actual sites, selected Ritz & Ghougassian, received a real DeepSeek response, downloaded two Pexels photographs, and passed quality validation. Final rendering fixes reused that saved live response and the downloaded photos rather than making another model request.

Browser checks: 1440px desktop and 390px mobile have no horizontal overflow; mobile navigation, FAQ, and ZIP download work; no JavaScript runtime errors were observed. Screenshots and reports are saved under `outputs/reference_live_20261029_603b0344/`. Google Places was not called in this migration test.
