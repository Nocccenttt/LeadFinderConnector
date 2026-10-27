# SEO-First Design and Landing Page Pipeline

LeadFinder now creates a planning trail before generating a landing page. Run the existing generator with a valid `AI_HANDOFF.json` and its sibling `business.json`:

```powershell
python deepseek_website_generator.py "path\to\client\AI_HANDOFF.json"
python website_validator.py "path\to\client"
```

## Pipeline stages

1. **Business facts** — `business.json` remains the source of truth. Missing facts are omitted rather than guessed.
2. **SEO strategy** — writes `SEO_STRATEGY.json` with a primary local keyword idea, secondary phrase ideas, verified location, suggested title/meta description, and content requirements.
3. **Design reference research** — attempts a category search on Admire The Web and writes `DESIGN_REFERENCES.json`. The request is time-limited and failure is non-fatal. References supplied in `AI_HANDOFF.json` under `design_references` are also included.
4. **Design blueprint** — writes `DESIGN_BLUEPRINT.json` with the intended hierarchy, responsive principles, and reference links.
5. **Content and visual direction** — passes the SEO strategy, design blueprint, and reference notes to DeepSeek, which generates page copy, SEO metadata, and proposed visual design tokens. Color values, font stacks, and radius values are allow-listed before they can affect CSS.
6. **Landing page generation** — writes `website/index.html`, `website/styles.css`, and `website/script.js`. The HTML includes title and meta description tags, Open Graph metadata, and LocalBusiness JSON-LD based only on available business fields. Validated design tokens are appended to the base stylesheet so the visual palette and typography can vary by project.
7. **SEO QA** — writes `SEO_QA_REPORT.json`; the website validator includes SEO checks in `quality_report.json`.

## SEO accuracy rules

- Keyword phrases are heuristic suggestions unless a real keyword data source is connected. The app must not invent search volume, keyword difficulty, traffic estimates, or ranking predictions.
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
