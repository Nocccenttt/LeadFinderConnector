# Color foundation

Color choices follow an explicit source hierarchy: supplied business brand colors,
then opaque colors measured on the selected reference. Model-proposed colors do
not override either source. With neither source, the foundation is unavailable;
it is not labeled reference-grounded.

Provide brand anchors in business.json or AI_HANDOFF.json:

```json
{"brand":{"colors":{"primary":"#2266FF","background":"#FFFFFF","text":"#202020"}}}
```

`color_foundation.py` preserves the supplied/measured anchor and derives OKLab
tonal ramps and semantic surface, text, action, border, and focus roles. Hover
and active states use these roles. Colors adjusted for readability remain
distinct from the original anchor in the manifest.

`COLOR_FOUNDATION.json` records source paths, anchor values, derivation, usage,
and exact foreground/background checks. The website includes the same manifest
as `color-tokens.json`. The renderer consumes semantic CSS variables as its last
color layer. The validator recalculates contrast instead of trusting saved PASS.

The targets are 4.5:1 for the specified text pairs and 3:1 for the specified
meaningful controls/focus pairs, without rounding to pass. These token tests do
not establish whole-page accessibility, particularly over photographs. See
[W3C text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
and [non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).

This fixes color provenance and consistency. It does not solve repetition in
page architecture; that limitation is recorded separately in
`REFERENCE_IMPLEMENTATION.json`.
