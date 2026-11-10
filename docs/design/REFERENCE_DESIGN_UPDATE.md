# Reference design update

## Composition renderer update

New generations now use a validated reference-mapped composition tree for every
included section. A dedicated architecture request receives the selected source
and actual content slots; it no longer inherits the old eight-section rendering
contract. See REFERENCE_COMPOSITION.md for schema, limits and verification.

Two real reference builds using identical pet-business copy and photographs now
render different hero structures, lower-page grouping and section selection.
The main pet preview uses the Rudolph Care build. Earlier fixed-section and
partial-transfer descriptions below apply to the saved legacy renderer.

## Current limitation found in the renderer

Reference discovery is functioning, but full reference transfer is incomplete.
`build_html` still draws the lower page from shared section markup. Several
composition labels apply only a width rule or use the baseline section layout.
Measured tokens and a researched URL do not prove fidelity or cross-site
uniqueness. `REFERENCE_IMPLEMENTATION.json` now reports that coverage explicitly;
`RENDERED_DESIGN.json` labels transfer partial and uniqueness unverified.

The geometry transfer now supports left/right image placement, unequal split
proportions, and overlapping full-width imagery. Monospace and humanist families
are retained as families with explicit fallback fonts. These are targeted fixes;
the larger remaining work is reference-driven lower-page architecture and visual
comparison across real generations.

The color system now uses explicit brand anchors or measured reference colors,
with semantic roles and derived interaction states. See COLOR_FOUNDATION.md.

The saved Rudolph Care screenshot also exposed a location modal, navigation
images, and an off-screen carousel slide in the original research capture.
Research now excludes navigation imagery, hidden ancestors and horizontally
off-screen elements, and resolves the explicit International (EUR) selector.
The refreshed capture identifies the source's full-width photographic hero;
the old split inference was contaminated by navigation imagery. The local pet
preview now uses the refreshed measurements. This supersedes the split-hero
description in the historical live-revision notes below.

Validation: 76 unit/regression tests pass. Browser checks pass at 1440px and
390px, including image loading, overflow, menu, FAQ, and computed action colors.
The capture filters were also exercised against a local browser fixture with
navigation images, transparent ancestors and off-screen slides. Full-page
reference fidelity and cross-site uniqueness remain unverified.

The previous pages shared a design because exact niche searches fell back to the same professional gallery, the AI chose the same architecture reference, and `full-width split hero` was incorrectly rendered as a background-image overlay. Several design choices were descriptive strings with no executable layout behavior.

## Changes

- Broaden sparse niche searches to adjacent terms before using the general gallery. Adjacent results are labeled as such; they are not presented as exact industry matches.
- Fetch the actual submitted sites and reject expired/domain-sale destinations.
- Use Playwright to measure rendered desktop typography, colors, spacing, controls, image positions, and section geometry. Save source screenshots outside the website folder in `REFERENCE_RESEARCH/`.
- Pass those measured observations into the design prompt. The text model receives computed measurements, not image vision input. Reference mobile behavior and motion remain unverified.
- Require a validated `render_layout` object. It controls hero structure, navigation alignment, benefits, process, FAQ, CTA treatment, button shape, heading family/scale, and image proportion.
- Implement split and centered-media heroes as different HTML structures. Split layouts take precedence over the ambiguous phrase `full-width split`.
- Implement list benefits, vertical steps, split FAQs, banner CTAs, and controlled typography with CSS specific to the saved layout contract.
- Support `generate_website(..., preserve_content=True)` and CLI `--design-only` so a design revision retains saved content and image queries. Saved image credits allow matching photos to be reused.
- Save `RENDERED_DESIGN.json` alongside the full model spec and reference evidence.

## Browser setup

Install requirements as usual. For a portable headless Chromium installation:

```powershell
python -m playwright install chromium
```

The research step tries Chromium, then installed Edge and Chrome. If browser research is unavailable, the candidate records that status instead of claiming rendered evidence.

## Live revision

Adventure with JJ Pet Grooming now uses the Rudolph Care entry on Admire The Web:

https://admiretheweb.com/inspiration/rudolph-care/

The run captured rendered reference measurements and generated a new design specification. The accepted saved content was compared field by field and remained unchanged. The final render changed the full-bleed photographic hero into a separate text/photo split, and changed heading typography, benefit layout, process orientation, FAQ layout, and CTA treatment.

The tree-service preview was not rewritten. The live preview remains local. Source screenshots and generated comparisons are stored under `outputs/reference_live_20261029_603b0344/`.

Validation: 59 tests pass. The regenerated page passes quality checks, mobile/desktop overflow checks, menu and FAQ checks, and ZIP packaging. The dashboard now offers REGENERATE DESIGN to keep saved content while generating a new design.

## Website-build foundation

Reference selection now prioritizes audience, tone, content structure, and service experience. A different industry is welcome when its website patterns transfer well. It no longer asks the model to change references merely for novelty.

`REFERENCE_BUILD_PLAN.json` connects the selected site's measured heading scale, type family, content width, section padding, button radius, and image geometry to bounded implementation tokens. These tokens are consumed by the renderer and included in the Elementor rebuild notes. A successful model-generated reference selection now requires rendered measurements.

The pet-grooming preview was rebuilt from its already captured Rudolph Care measurements and approved content; no new model request was needed for this refinement. The build uses a 1198px container, a measured 92px heading cap, 86px desktop section rhythm, square controls, and the reference's landscape image proportion. Body copy has a 17px readability minimum. Libre Caslon Display and Libre Caslon Text are bundled locally with their OFL licenses as substitutes for the source's proprietary serif fonts.

Current validation: 63 tests pass. Local fonts load, desktop/mobile layouts have no horizontal overflow, the menu and FAQ work, and the business copy remains unchanged. Source screenshots remain research artifacts outside the downloadable website folder.
