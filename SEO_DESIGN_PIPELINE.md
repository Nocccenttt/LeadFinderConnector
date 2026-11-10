# SEO-First Design and Landing Page Pipeline

LeadFinder now creates a planning trail before generating a landing page. Run the existing generator with a valid `AI_HANDOFF.json` and its sibling `business.json`:

```powershell
python reference_website_generator.py "path\to\client\AI_HANDOFF.json"
python website_validator.py "path\to\client"
```

## Pipeline stages

1. **Business facts** — `business.json` remains the source of truth. Missing facts are omitted rather than guessed.
2. **SEO strategy** — writes `SEO_STRATEGY.json` with a primary local keyword idea, secondary phrase ideas, verified location, suggested title/meta description, and content requirements.
3. **Design reference research** - the active archived generator uses Admire as a discovery hub, extracts the actual submitted websites, and fetches bounded HTML/CSS research. Curated handoff references are tried first. The research records headings, text snapshots, colors, fonts, and layout-rule counts; rendered desktop measurements and source screenshots are also captured when a browser is available. The text model receives measurements rather than image vision input. Writes `DESIGN_REFERENCES.json`.
4. **Design blueprint** - DeepSeek selects one researched actual website and returns the reference analysis, design system, section order, and composition. Writes `DESIGN_BLUEPRINT.json` and `website/design_spec.json`.
5. **Content and visual direction** - generates category-specific copy and image queries. When no services are verified, a factual-copy guard replaces unsupported service claims with neutral contact guidance while retaining the selected visual design.
6. **Landing page generation** - renders the archived photographic hero variants, validated palette, section tones, typography, and validated executable layout choices. See `REFERENCE_DESIGN_UPDATE.md` for layout modes and design-only regeneration. Downloads Pexels photos into `website/images/`; failed photo requests use the logged placeholder fallback. Generates HTML, CSS, JavaScript, safe LocalBusiness JSON-LD, and a configured canonical when supplied. See `GENERATOR_MIGRATION.md` for the active source and migration repairs.
7. **SEO QA** — writes `SEO_QA_REPORT.json`; the website validator includes SEO checks in `quality_report.json`.

## SEO accuracy rules

- Keyword phrases, including service-plus-location variants, are heuristic suggestions unless a real keyword data source is connected. The app must not invent search volume, keyword difficulty, traffic estimates, or ranking predictions.
- Do not create unverified service areas or location pages.
- Do not invent services, reviews, ratings, awards, certifications, prices, guarantees, business history, or outcomes.
- Use one H1, logical H2/H3 sections, natural keyword use, descriptive metadata, and useful FAQs only when source facts support them.
- Structured data contains only available business name, address, phone, email, and an existing HTTP(S) website URL. It does not claim that the generated preview has a production URL.
- A canonical link is emitted only when a valid canonical URL is explicitly supplied through `business.json` or `AI_HANDOFF.json` under `seo.canonical_url`. Do not publish placeholder canonicals.
- Meaningful images require descriptive alt text; decorative images should use empty alt text. The QA flags missing alt attributes.
- Admire The Web availability and the quality of discovered references can vary. Review the saved reference URLs manually before relying on them. Do not copy reference-site copy, logos, or proprietary assets.

## Output files per client

- `SEO_STRATEGY.json`
- `DESIGN_REFERENCES.json`
- `DESIGN_BLUEPRINT.json`
- `SEO_QA_REPORT.json`
- `website/index.html`
- `website/styles.css`
- `website/script.js`
- `quality_report.json` after running `website_validator.py`

## Validation

Run the regression suite:

```powershell
python -m unittest discover -s tests -v
```

The SEO checks assess page implementation and content structure; they do not guarantee search-engine indexing or rankings.
