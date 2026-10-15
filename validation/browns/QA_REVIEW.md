# Brown's Tree Service baseline — 15 October 2026

Reference: Ragged Edge (`https://raggededge.com`), selected explicitly after live
Admire discovery returned four current submitted sites. The historical four V7
examples are retained in offline extraction regressions; the live hub currently
lists different submissions, as recorded in `reference_candidates.json`.

The supplied Brown's website returned HTTP 403 across its URL variants. The user
authorized a minimal site using verified handoff name, address and phone. The
saved content therefore has no service catalog, credentials, reviews, process or
FAQ. Photographs are credited illustrative stock, not verified Brown's projects.

The final live DeepSeek response produced `design_spec.json`. The production
generator consumed it directly, producing the exact site in `website/`.
The context hash binds that spec to the saved reference analysis and business.

## Visual review

Desktop (1440px), tablet (834px) and mobile (390px) screenshots were inspected.
The rendered result visibly applies the spec's full-bleed hero, large sans-serif
hierarchy, uneven image/text columns, wide whitespace, restrained color roles and
contact-focused composition. Mobile stacks the image after copy and exposes a
working native navigation menu. Local and contact sections follow split layouts
on larger screens and stack on mobile. No unsupported business claims were added.

| Reference principle | Observed transfer |
| --- | --- |
| Viewport-spanning visual opening | Brown's uses its own illustrative arborist photo, full-bleed, with a legible text overlay. |
| Strong sans-serif headline hierarchy | Reference H1 samples measure 82px desktop / 44px mobile; Brown's uses 72px / 44px with 1.1 leading. |
| Generous section rhythm | Source evidence includes large section padding; Brown's adapts that to 120px desktop / 64px mobile. |
| Fixed navigation with scroll behavior | Adapted as an accessible sticky solid header rather than reproducing source choreography. |
| Brief transitions | Brown's uses 300ms fade reveals and hover lifts; reduced-motion disables them. |

This is a transfer of selected principles, not a reconstruction or a pixel-match
claim. The source's animation-heavy initial captures leave several project media
areas blank; static CSS also includes unused form-library styles. Those limits
are retained in the analysis. A proprietary typeface pairing, original video,
complete scroll choreography and exact brand treatments are not reproduced.
Asymmetry is the Director's adaptation, rather than a proven measured source
column system. The source H1 is below its first visual panel, not inside it;
the Director's brief description of a hero headline is interpretive.

## Validation

- Six offline regression tests pass (`python -m unittest test_design_pipeline`).
- All 32 final browser checks pass, including order, typography scaling, image
  loading, no overflow, CTA visibility, mobile menu, reveal animation, hover and
  reduced-motion behavior. See `visual_qa.json` and `visual_qa_evidence.json`.
- Contrast is validated before rendering for background/text, surface/text and
  accent/button text. The full-bleed hero's derived dark text panel is recorded
  in `website/render_manifest.json`.
- `git diff --check` passes.

The saved screenshots and browser evidence refer to the original handoff output
location where QA ran. This folder contains an identical copy of the reviewed
site and its assets for review from a clean checkout.

Regenerate this contact-only baseline without new API calls:

```powershell
python deepseek_website_generator.py validation/browns/AI_HANDOFF.json --handoff-only
```

Refresh live discovery/analysis/spec using the flags in `DESIGN_PIPELINE.md`.
Subjective similarity remains a visual review decision; the automated report
establishes spec application and usability checks.
