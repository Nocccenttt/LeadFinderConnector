"""Turn a researched website into a traceable, bounded implementation plan."""
from pathlib import Path
from statistics import median
import re
import shutil


def _number(value, fallback):
    try:
        return float(re.search(r"-?\d+(?:\.\d+)?", str(value)).group())
    except (AttributeError, ValueError, TypeError):
        return fallback


def _bounded(value, low, high):
    return round(max(low, min(high, value)))


def _font_family(value):
    value = str(value).lower()
    if "monospace" in value:
        return "monospace"
    if "serif" in value and "sans-serif" not in value:
        return "serif"
    if any(name in value for name in ("trebuchet", "humanist", "gill sans", "optima")):
        return "humanist"
    return "system"


def _section_metrics(section):
    padding = str(section.get("padding") or "80px").split()
    images = section.get("section_layouts", {}).get("images", [])
    image = next((item.get("rect", {}) for item in images if _number(item.get("rect", {}).get("width"), 0) > 100), {})
    return {"padding_top_px": _bounded(_number(padding[0], 80), 24, 160),
            "padding_bottom_px": _bounded(_number(padding[2] if len(padding) >= 3 else padding[0], 80), 24, 160),
            "image_ratio": round(max(.5, min(2.5, _number(image.get("width"), 4) / max(1, _number(image.get("height"), 3)))), 3)}


def reference_build_plan(design, candidates):
    selected = design.get("reference_selection", {}).get("website_url")
    candidate = next((item for item in candidates if item.get("website_url") == selected), None)
    if candidate is None:
        return None
    observed = candidate.get("rendered_desktop", {})
    if observed.get("status") != "measured":
        return {"status": "unmeasured", "source_url": selected,
                "note": "No rendered measurements; the page uses the declared design specification."}
    viewport = observed.get("viewport", {})
    width = _number(viewport.get("width"), 1440)
    height = _number(viewport.get("height"), 1000)
    headings = observed.get("headings", [])
    primary = next((item for item in headings if item.get("tag") == "H1"), headings[0] if headings else {})
    body = observed.get("body", {})
    secondary = [item for item in headings if item.get("tag") == "H2" and _number(item.get("size"), 0) >= 28]
    section_padding = [_number(item.get("padding"), 0) for item in observed.get("sections", [])]
    section_padding = [value for value in section_padding if value > 24]
    section_space = median(section_padding) if section_padding else 80
    heading_rect = primary.get("rect", {})
    gutter = _number(heading_rect.get("x"), width * .08)
    controls = observed.get("controls", [])
    control_radius = median([_number(item.get("radius"), 0) for item in controls]) if controls else 0
    font = str(primary.get("font", "")).lower()
    heading_family = _font_family(font)
    body_font = str(body.get("font", "")).lower()
    body_family = _font_family(body_font)
    images = [item for item in observed.get("images", [])
              if 0 <= _number(item.get("rect", {}).get("y"), height + 1) < height
              and _number(item.get("rect", {}).get("width"), 0) > width * .2]
    image_right = any(_number(item.get("rect", {}).get("x"), 0) >= width * .4
                      and _number(item.get("rect", {}).get("width"), width) < width * .8 for item in images)
    image_below = images and min(_number(item.get("rect", {}).get("y"), 0) for item in images) > _number(heading_rect.get("y"), 0) + _number(heading_rect.get("height"), 0)
    suggested_hero = "split" if image_right and gutter < width * .3 else "centered-media" if image_below else None
    dominant_image = max(images, key=lambda item: _number(item.get("rect", {}).get("width"), 0) * _number(item.get("rect", {}).get("height"), 0)) if images else None
    image_rect = dominant_image.get("rect", {}) if dominant_image else {}
    image_side = "right"
    split_columns = [1, 1]
    if dominant_image and heading_rect:
        ix, iy = _number(image_rect.get("x"), 0), _number(image_rect.get("y"), 0)
        iw, ih = _number(image_rect.get("width"), 0), _number(image_rect.get("height"), 0)
        hx, hy = _number(heading_rect.get("x"), 0), _number(heading_rect.get("y"), 0)
        hw, hh = _number(heading_rect.get("width"), 0), _number(heading_rect.get("height"), 0)
        vertical_overlap = min(iy + ih, hy + hh) - max(iy, hy)
        # Disjoint horizontal boxes on the same row provide actual split evidence.
        if vertical_overlap > 0 and (ix + iw <= hx + 12 or hx + hw <= ix + 12):
            suggested_hero = "split"
            image_side = "left" if ix < hx else "right"
            ratio = max(.5, min(2, iw / max(hw, 1)))
            split_columns = [round(ratio, 3), 1] if image_side == "left" else [1, round(ratio, 3)]
        elif iw >= width * .85 and vertical_overlap > 0:
            suggested_hero = "full-bleed"
    image_ratio = _number(image_rect.get("width"), 4) / max(1, _number(image_rect.get("height"), 3))
    tokens = {
        "container_px": _bounded(width - 2 * gutter, 1040, 1320),
        "heading_px": _bounded(_number(primary.get("size"), 80), 60, 96),
        "section_heading_px": _bounded(median([_number(item.get("size"), 42) for item in secondary]) if secondary else 42, 32, 56),
        "heading_weight": _bounded(_number(primary.get("weight"), 500), 400, 800),
        "body_px": _bounded(_number(body.get("size"), 17), 17, 19),
        "section_space_px": _bounded(section_space, 56, 104),
        "layout_gap_px": _bounded(section_space * .55, 32, 64),
        "button_radius_px": _bounded(control_radius, 0, 24),
        "heading_family": heading_family,
        "body_family": body_family,
        "image_ratio": round(max(.75, min(1.78, image_ratio)), 3),
        "hero_image_side": image_side,
        "hero_columns": split_columns,
    }
    return {
        "status": "grounded", "source_url": selected, "source_entry": candidate.get("hub_url"),
        "selection_fit": design.get("reference_fit") or {"reason": design.get("reference_selection", {}).get("reason", "")},
        "selection_rule": "Transfer page architecture, visual tone, and service experience; exact industry is optional.",
        "tokens": tokens, "suggested_hero": suggested_hero,
        "section_metrics": [_section_metrics(section) for section in observed.get("sections", [])],
        "implementation_scope": "Measured tokens and supported layout primitives; not a bespoke reconstruction of the reference.",
        "limitations": ["Lower-page architecture still uses the shared section renderer.",
                        "Font substitutions preserve broad family, not the original typeface.",
                        "Uniqueness across generated sites is not currently verified."],
        "evidence": {
            "heading": {key: primary.get(key) for key in ("font", "size", "weight", "rect")},
            "body": {key: body.get(key) for key in ("font", "size", "lineHeight")},
            "section_padding_px": section_padding, "control_radius_px": control_radius,
            "hero_image_geometry": [item.get("rect") for item in images],
        },
        "adaptations": ["Original business content and photographs replace the source brand and assets.",
                        "Body text is kept at least 17px for readability.",
                        "Measurements are bounded for the available content and responsive layout.",
                        "Libre Caslon fonts substitute for proprietary display/body serifs when that family is observed."],
    }


def install_reference_fonts(output_dir, plan):
    if not plan or plan.get("status") != "grounded":
        return
    if "serif" not in (plan["tokens"]["heading_family"], plan["tokens"]["body_family"]):
        return
    source = Path(__file__).resolve().parent / "assets" / "fonts"
    target = Path(output_dir) / "fonts"
    target.mkdir(exist_ok=True)
    for filename in ("LibreCaslonDisplay-Regular.ttf", "LibreCaslonText.ttf", "LibreCaslonDisplay-OFL.txt", "LibreCaslonText-OFL.txt"):
        shutil.copy2(source / filename, target / filename)


def reference_build_css(plan):
    if not plan or plan.get("status") != "grounded":
        return ""
    tokens = plan["tokens"]
    # Rebound values at the rendering boundary as well as when building a plan.
    limits = {"container_px": (1040, 1320), "heading_px": (60, 96), "section_heading_px": (32, 56),
              "body_px": (17, 19), "section_space_px": (56, 104), "layout_gap_px": (32, 64),
              "button_radius_px": (0, 24), "heading_weight": (400, 800)}
    t = {key: _bounded(_number(tokens.get(key), low), low, high) for key, (low, high) in limits.items()}
    serif_heading = tokens.get("heading_family") == "serif"
    serif_body = tokens.get("body_family") == "serif"
    fonts = {"system": "Arial, Helvetica, sans-serif", "humanist": "'Trebuchet MS', Arial, sans-serif",
             "monospace": "'Courier New', monospace"}
    heading_font = "'Reference Display', Georgia, serif" if serif_heading else fonts.get(tokens.get("heading_family"), fonts["system"])
    body_font = "'Reference Text', Georgia, serif" if serif_body else fonts.get(tokens.get("body_family"), fonts["system"])
    columns = tokens.get("hero_columns", [1, 1])
    if not isinstance(columns, list) or len(columns) != 2:
        columns = [1, 1]
    columns = [max(.5, min(2, _number(value, 1))) for value in columns]
    image_side = tokens.get("hero_image_side", "right")
    image_ratio = max(.75, min(1.78, _number(tokens.get("image_ratio"), 1.333)))
    faces = ""
    if serif_heading or serif_body:
        faces = """@font-face{font-family:'Reference Display';src:url('fonts/LibreCaslonDisplay-Regular.ttf') format('truetype');font-weight:400;font-display:swap;}
@font-face{font-family:'Reference Text';src:url('fonts/LibreCaslonText.ttf') format('truetype');font-weight:400 700;font-display:swap;}"""
    return faces + f"""
/* Implemented from the selected reference's rendered evidence. */
:root{{ --max:{t['container_px']}px; --font-heading:{heading_font}; --font-body:{body_font};
--section-space:{t['section_space_px']}px; --compact-space:{round(t['section_space_px']*.75)}px; }}
body{{font-family:var(--font-body);font-size:{t['body_px']}px;line-height:1.65;}}
body h1{{font-family:var(--font-heading);font-size:clamp(3.2rem,5.6vw,{t['heading_px']}px);font-weight:{400 if serif_heading else t['heading_weight']};letter-spacing:-.035em;line-height:1.02;}}
body h2{{font-size:clamp(2rem,3.5vw,{t['section_heading_px']}px);font-weight:{400 if serif_heading else t['heading_weight']};letter-spacing:-.03em;line-height:1.12;}}
body h3{{font-size:1.35rem;font-weight:500;letter-spacing:-.015em;}}
body .button,body .button.primary{{font-family:var(--font-body);font-weight:500;border-radius:{t['button_radius_px']}px;}}
.hero-split .hero-grid{{column-gap:{t['layout_gap_px']}px;}}
.hero-split .hero-grid{{grid-template-columns:minmax(0,{columns[0]}fr) minmax(0,{columns[1]}fr);}}
.hero-split .hero-content{{grid-column:{2 if image_side == 'left' else 1};grid-row:1;}}
.hero-split .hero-visual{{grid-column:{1 if image_side == 'left' else 2};grid-row:1;}}
.hero-split{{padding-block:{t['section_space_px']}px;}}
body[data-hero-image] .hero-split .hero-photo img{{height:auto;aspect-ratio:{image_ratio};max-height:680px;}}
body[data-process="vertical"] [data-section="process"]>.container,
body[data-faq="split"] [data-section="faq"]>.container{{column-gap:{t['layout_gap_px']}px;}}
body .service-card,body .location-box,body .about-image img{{box-shadow:none;}}
body .eyebrow{{font-family:var(--font-body);font-weight:500;letter-spacing:.1em;}}
@media(max-width:950px){{.hero-split .hero-grid{{grid-template-columns:1fr;}}.hero-split .hero-content,.hero-split .hero-visual{{grid-column:auto;grid-row:auto;}}}}
@media(max-width:600px){{body h1{{font-size:clamp(2.8rem,11.5vw,3.6rem);}}body{{font-size:17px;}}.hero-split{{padding-block:44px;}}body[data-hero-image] .hero-split .hero-photo img{{max-height:380px;}}}}
"""
