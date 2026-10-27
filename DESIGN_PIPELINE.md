# Reference-driven website generation

The production entry point is `deepseek_website_generator.py`. No experimental
generator copies are needed. Business facts govern content; measured reference
principles inform a validated spec; the spec governs rendering.

## Setup

Install `requirements.txt` into your Python environment and set
`DEEPSEEK_API_KEY` in `.env`, or pass `--env-file PATH`. Rendered analysis and QA
also need Node.js and Playwright (`npm install playwright`). The browser helper
uses Playwright's Chromium or an installed Chrome/Edge. If none is available,
run `npx playwright install chromium`. An existing Playwright installation can
be used through `NODE_PATH`. These are tooling dependencies, not website assets.

## Checkpoints

Run from this repository, replacing HANDOFF with the target AI_HANDOFF.json:

```powershell
python deepseek_website_generator.py HANDOFF --reference-analysis-only --reference-url https://raggededge.com
python deepseek_website_generator.py HANDOFF --design-only --handoff-only
python deepseek_website_generator.py HANDOFF --handoff-only
python deepseek_website_generator.py HANDOFF --visual-qa-only
python -m unittest test_design_pipeline
```

For Brown's, HANDOFF is
`"codex_handoffs/HIGH/Brown's Tree Service/AI_HANDOFF.json"`.
The normal generation command automatically creates missing analysis/spec
checkpoints before rendering. For a reviewable workflow, run reference analysis
first, inspect its viewport screenshots and evidence, create the design spec,
then render the site. `--reference-url URL` analyzes that public website directly
and skips gallery discovery; a reference already assigned to another lead is
rejected. Without an explicit reference, the generator selects an unused site
from the live Admire The Web gallery using a stable per-business starting point.
Explicit `--reference-index N` remains available for controlled runs and also
rejects references assigned to another lead. `--refresh-reference` re-analyzes
the selected reference and regenerates the design spec. Changing the reference
also invalidates the prior design spec, including when saved source-backed
business content is used. The design director receives the references and style
directions already assigned to other leads so it can build a distinct visual
direction for each business.

The LeadFinder dashboard exposes the same optional visual reference URL in the
Landing Page Demo panel. Leave it blank to automatically choose a reference not
already assigned to another lead for a new handoff.

Artifacts beside the handoff:

1. `reference_candidates.json`: four distinct submitted sites from the live hub,
   or an empty list when a URL was selected directly.
2. `selected_reference.json`: the chosen site and discovery or explicit source.
3. `reference_analysis.json`: CSS signals plus computed samples at 1440, 834 and
   390 pixels. Browser analysis ties the hero and CTA to visible top-of-page
   elements and saves top-viewport and full-page screenshots.
   `reference_browser_evidence.json` and `reference-*.png` retain rendered
   evidence. Analysis excludes source copy, image URLs and logos.
4. `design_spec.draft.json`: raw Director response for diagnosing invalid tokens.
   `design_spec.json`: validated version 2 tokens and reference influence mappings.
   `design_context.json` binds the spec to business facts, analysis and source mode.
5. `website/`: HTML, CSS, JS, business imagery, its actual `design_spec.json`, and
   `render_manifest.json` listing realized and omitted sections.
6. `visual_qa.json`, `visual_qa_evidence.json`, `qa-*.png`: browser checks and visual
   review evidence. Check desktop, tablet and mobile screenshots manually too.

Reference analysis mode performs no DeepSeek call. `--static-analysis` explicitly
opts into weaker HTML/CSS evidence when browser tooling is unavailable. CSS rules
include inactive library defaults; rendered samples take precedence. Captures
cannot completely reconstruct hover intent, background-video frames or complex
scroll choreography. Failed fetches and evidence limits remain observable.

## Renderer contract and guardrails

`DEFAULT_DESIGN_SPEC`, `DESIGN_ENUMS` and `DESIGN_RANGES` define the contract in
the production generator. Missing values receive neutral defaults. Invalid
types, arbitrary CSS/HTML, unsupported compositions, duplicate sections and
low-contrast role pairs fail before site files are written. Hero comes first and
contact last; the Director controls all intervening sections and their order.

Supported hero modes: editorial, split, full-bleed and contained. Section
compositions: split, overlap, rows, grid and feature; width and color tone are
independent. A section layout labelled full-bleed is normalized to feature layout
with full-bleed width. Colors are named roles, never sorted by lightness; business
palette hints cannot override the Director's final roles. Generic font stacks
provide category/scale/weight contrast without copying proprietary fonts.
Navigation, spacing, card/button treatment, mobile stacking and motion follow
validated tokens. Reduced-motion preferences take precedence. Full-bleed image
heroes may add a dark text panel to maintain legibility; the manifest records it.

Services, proof, galleries, testimonials, process and FAQ render only when their
grounded content exists. Process and FAQ accept first-party `research.process`
(`title`, `text`) and `research.faq` (`question`, `answer`) records; the current
crawler does not fabricate them. There is no form without a configured backend.

For a content-preserving redesign, use `--content-file PATH` with a source-backed
JSON content file. The file must name the business exactly and list its source
URLs. Services, process and FAQ records are retained in full; rendering fails if
the spec would omit them. Subsequent ordinary runs reuse this saved content.
Contact-only mode refuses to overwrite existing substantive content.

Brown's restored full-content baseline now runs with:

```powershell
python deepseek_website_generator.py validation/browns/AI_HANDOFF.json --content-file validation/browns/restored_content.json
```

`--handoff-only` is an explicit contact-only mode for inaccessible business sites.
It uses fixed factual copy, omits services/reviews/claims, and requires no DeepSeek
copy request. Reference design still uses DeepSeek. Tree stock photography is
labelled illustrative, credited, and uses existing repository assets. It is not
presented as Brown's actual work. Omit the flag when first-party research is usable.

Generated handoff artifacts remain ignored by the repository's existing policy.
The reviewed Brown's evidence baseline is retained under `validation/browns/`.
No credentials are committed.
