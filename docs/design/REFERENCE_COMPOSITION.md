# Reference composition

New generations use `design_spec.page_blueprint` as the section architecture.
The reference can determine grouping, image placement, unequal columns, collections,
overlays, order, and which sections appear. The old shared section layouts remain
available to saved designs without a blueprint.

The content renderer supplies named, escaped content slots. The composition tree
arranges those slots; it cannot introduce HTML, CSS, URLs, or business claims.
Required slots cannot be omitted or repeated within an included section.
Omitting a redundant section changes presentation; design-only generation still
preserves every saved copy field and image query in GENERATED_COPY.json.

## Generation

The first model request selects the reference and produces copy/theme metadata.
A dedicated architecture request receives only that selected site's measured
sections, explicit source indices, available copy, and the exact slot inventory.
Separating this request prevents the legacy eight-section schema from dictating
the new architecture. One correction request is allowed for invalid output;
another invalid response fails generation without a silent template fallback.
Model responses are saved in REFERENCE_RESEARCH, and composition usage is logged
separately in logs/api_usage.json.

Each blueprint section names a real measured source index and explains its
adaptation. Source research includes child geometry, heading/image positions,
grid tracks, gaps, and text alignment. The renderer transfers source section
padding and image proportions through the build plan. All grids stack on mobile
in DOM reading order.

Example layout tree inside a section:

```json
{"type":"grid","columns":[1.2,0.8],"gap":48,"align":"start","children":[
  {"type":"stack","gap":24,"children":[{"slot":"title"},{"slot":"text"}]},
  {"slot":"image"}
]}
```

Sections choose semantic canvas/subtle/brand tones from the color foundation.
`REFERENCE_IMPLEMENTATION.json` records the source mappings and structure
signature. The downloadable website includes `page-blueprint.json` and Elementor
container instructions. Navigation links follow sections actually present.
Validation checks blueprint/source mappings and rendered section coverage.

## Verification

Two real architecture requests used the same approved pet-business copy and
photos, with refreshed Rudolph Care and Stripe Careers measurements respectively.
The outputs have different hero structures, benefit columns, section selections,
typography and source-derived palettes. Both passed 1440px/390px browser checks,
loaded images, menu/FAQ interactions and specified action contrast pairs.
The main preview ZIP contains the blueprint, semantic colors and font licenses.
Results and screenshots live in the ignored outputs test workspace.

This verifies two distinct reference-driven builds. It does not establish that
every future generation is unique or reconstruct the source site's full visual
behavior. Structure signatures support comparison; no global duplicate registry
is currently enforced. Reference mobile behavior and motion remain unmeasured.

Run all checks, including browser checks (requires Playwright Chromium):

```powershell
$env:RUN_BROWSER_TESTS='1'
python -m unittest discover -s tests -q
```
