# Approved craft profile and multi-business test

The approved modern-minimal preview principles now run in the generator through
`premium_craft.py` and `assets/craft-interactions.js`. Body and display typography
use bundled Geist with its OFL license. References still determine composition
and the source-based color foundation determines each palette.

| Before | After | Why |
| --- | --- | --- |
| Sparse leads receive identical contact paragraphs | Grounded marketing and category-specific guidance retained | Prevent copy repetition |
| Thin serif body/display combination | Approved sans-serif hierarchy and readable body copy | Preserve the approved direction |
| Automatic tinted hero adaptation | Separate hero image/text required for new compositions | Keep photographs clear |
| Repeated about/feature photo | About image optional when a feature uses the second photo | Avoid duplicated imagery |
| Older hover and keyboard transitions | Pointer press feedback, immediate keyboard state, reduced-motion cancellation | Deliberate interaction |
| Blank reference accepted as measured | Readable section evidence required; broader discovery when unavailable | Ground the composition in an actual render |

New optional `feature` and `guide` sections use supplied content slots. They are
not appended to every page: the architecture model chooses sections and grouping
from the reference and available content. Draft marketing copy excludes services
not in the verified service list. `copy_grounding.py` checks unsupported claim
patterns; this is not exhaustive factual verification or publication approval.

Marketing introductions run once through IntersectionObserver/WAAPI using opacity
and transform, 560ms strong ease-out, and short 60ms staggers. Keyboard navigation
cancels/prevents them, reduced-motion preferences cancel them, and content is
visible without JavaScript. Pointer press feedback uses 140ms transform transitions.

## Reusing captured evidence

Set `reuse_reference_research` in a handoff only when the existing
`REFERENCE_RESEARCH/CANDIDATES.json` should be reused. Normal generation performs
fresh discovery. This cache only accepts candidates with readable measured sections.
With content-preserving generation and that flag, the saved selected reference
and approved copy go directly to the architecture request; copy is not rewritten.

## Actual test sample — 2026-11-07

Five recorded business inputs were tested: pet grooming, tree service, digital
marketing, and two roofing businesses. Categories missing in older records were
annotated from their explicit business names for these isolated test copies.
No services, prices, reviews or credentials were added to source records.

All five passed pipeline validation and browser checks at 320, 390, 768, 1024
and 1440 pixels. Checks included image loading, local fonts, contact numbers,
internal anchors, header collisions, mobile menu/Escape, FAQ keyboard operation,
runtime errors and action contrast. The original approved manual preview was
kept separate. Generated files and screenshots remain in ignored local outputs.

The comparison found **five full-page structures, but one shared opening family**:
all five used a headline above a separate photo. Copy differed substantially
after business names/contact facts were masked. This proves variation in this
sample; it does not prove universal or complete visual uniqueness. The repeated
opening remains an explicit design limitation pending the user's preference.

`design_comparison.py` ignores colors, spacing, radii, widths, source indices and
redundant stack wrappers when counting structures. It reports opening families
separately and compares identity-masked five-word copy overlaps. Use it alongside
rendered review:

```powershell
python design_comparison.py path/to/business-a path/to/business-b --output comparison.json
$env:RUN_BROWSER_TESTS='1'
python -m unittest discover -s tests -v
```

GitHub Actions now installs Chromium and runs browser checks as well as unit
regressions. Live model/image API calls are not made in CI.
