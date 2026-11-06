"""Source-based color primitives, OKLab tones, semantic roles, and contrast checks."""
import math
import re


def normalize_color(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        return "#" + "".join(char * 2 for char in value[1:]).upper()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.upper()
    match = re.fullmatch(r"rgba?\(([^)]+)\)", value, re.I)
    if not match:
        return None
    parts = [part for part in re.split(r"[,/\s]+", match.group(1).strip()) if part]
    if len(parts) not in (3, 4):
        return None
    try:
        channels = [float(part[:-1]) * 2.55 if part.endswith("%") else float(part) for part in parts[:3]]
        alpha = (float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])) if len(parts) == 4 else 1
    except ValueError:
        return None
    if alpha != 1 or any(not math.isfinite(channel) or not 0 <= channel <= 255 for channel in channels):
        return None
    return "#" + "".join(f"{round(channel):02X}" for channel in channels)


def _linear(color):
    color = normalize_color(color)
    if color is None:
        raise ValueError("Expected an opaque hex or RGB color")
    rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    return tuple(value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in rgb)


def contrast(first, second):
    def luminance(color):
        return sum(channel * weight for channel, weight in zip(_linear(color), (.2126, .7152, .0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


def _lab(color):
    red, green, blue = _linear(color)
    ell = (.4122214708 * red + .5363325363 * green + .0514459929 * blue) ** (1 / 3)
    em = (.2119034982 * red + .6806995451 * green + .1073969566 * blue) ** (1 / 3)
    ess = (.0883024619 * red + .2817188376 * green + .6299787005 * blue) ** (1 / 3)
    return (.2104542553 * ell + .7936177850 * em - .0040720468 * ess,
            1.9779984951 * ell - 2.4285922050 * em + .4505937099 * ess,
            .0259040371 * ell + .7827717662 * em - .8086757660 * ess)


def _rgb(lightness, a, b):
    ell = (lightness + .3963377774 * a + .2158037573 * b) ** 3
    em = (lightness - .1055613458 * a - .0638541728 * b) ** 3
    ess = (lightness - .0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * ell - 3.3077115913 * em + .2309699292 * ess,
            -1.2684380046 * ell + 2.6097574011 * em - .3413193965 * ess,
            -.0041960863 * ell - .7034186147 * em + 1.7076147010 * ess)


def _hex_lab(lightness, a, b):
    # Reduce chroma until the tone fits sRGB instead of clipping its hue.
    lightness = max(0, min(1, lightness))
    low, high = 0.0, 1.0
    for unused in range(20):
        scale = (low + high) / 2
        if all(-1e-7 <= value <= 1.0000001 for value in _rgb(lightness, a * scale, b * scale)):
            low = scale
        else:
            high = scale
    channels = _rgb(lightness, a * low, b * low)
    srgb = [12.92 * value if value <= .0031308 else 1.055 * max(0, value) ** (1 / 2.4) - .055 for value in channels]
    return "#" + "".join(f"{round(max(0, min(1, value)) * 255):02X}" for value in srgb)


def mix(first, second, amount):
    one, two = _lab(first), _lab(second)
    return _hex_lab(*(a + (b - a) * amount for a, b in zip(one, two)))


def tone(color, lightness):
    unused, a, b = _lab(color)
    return _hex_lab(lightness, a, b)


def _accessible(color, backgrounds, minimum):
    if all(contrast(color, background) >= minimum for background in backgrounds):
        return color
    lightness = _lab(color)[0]
    for value in sorted((step / 100 for step in range(101)), key=lambda value: abs(value - lightness)):
        adjusted = tone(color, value)
        if all(contrast(adjusted, background) >= minimum for background in backgrounds):
            return adjusted
    raise ValueError("The supplied surfaces cannot share an accessible foreground")


def _on(background, preferred):
    for color in preferred:
        if color and contrast(color, background) >= 4.5:
            return color
    return max(("#000000", "#FFFFFF"), key=lambda color: contrast(color, background))


def _scale(color):
    return {str(step): tone(color, lightness) for step, lightness in (
        (50, .98), (100, .95), (200, .90), (300, .83), (400, .75),
        (500, .65), (600, .55), (700, .45), (800, .36), (900, .27), (950, .20))}


def _brand_inputs(business, handoff):
    for source_name, source in (("business", business), ("handoff", handoff)):
        brand = source.get("brand", {})
        colors = brand.get("colors") if isinstance(brand, dict) else None
        location = source_name + ".brand.colors" if isinstance(colors, dict) else source_name + ".brand_colors"
        colors = colors if isinstance(colors, dict) else source.get("brand_colors", {})
        if isinstance(colors, dict) and colors:
            result = {}
            for role in ("primary", "background", "text"):
                if role in colors:
                    value = normalize_color(colors[role])
                    if not value:
                        raise ValueError(f"Brand {role} must be an opaque hex or RGB color")
                    result[role] = value
            if result:
                return result, location
    return {}, None


def build_color_foundation(business, handoff, design, references):
    brand, brand_location = _brand_inputs(business, handoff)
    url = design.get("reference_selection", {}).get("website_url")
    reference = next((item for item in references if item.get("website_url") == url), {})
    observed = reference.get("rendered_desktop", {})
    if observed.get("status") != "measured":
        observed = {}
    body = observed.get("body", {})
    canvas = brand.get("background") or normalize_color(body.get("background")) or normalize_color(observed.get("canvas_background"))
    text = brand.get("text") or normalize_color(body.get("color")) or next(
        (color for item in observed.get("headings", []) if (color := normalize_color(item.get("color")))), None)
    if not brand and (not canvas or not text):
        return {"status": "unavailable", "reason": "No explicit brand colors or measured reference canvas/text colors. An AI palette is not a color foundation."}
    canvas = canvas or "#FFFFFF"
    text = text or _on(canvas, ("#181818", "#FFFFFF"))
    anchors = []
    for kind in ("controls", "sections"):
        for index, item in enumerate(observed.get(kind, [])):
            color = normalize_color(item.get("background"))
            if not color or contrast(color, canvas) < 3:
                continue
            unused, a, b = _lab(color)
            chroma = math.hypot(a, b)
            rect = item.get("rect", {})
            area = float(rect.get("width", 0)) * float(rect.get("height", 0))
            anchors.append((chroma > .025, kind == "controls", chroma, area, color,
                            normalize_color(item.get("color")), f"rendered_desktop.{kind}[{index}].background"))
    best = max(anchors, key=lambda item: item[:4], default=None)
    anchor = brand.get("primary") or (best[4] if best else text)
    paired_text = best[5] if best else canvas
    anchor_source = brand_location + ".primary" if brand.get("primary") else best[6] if best else "rendered reference text (monochrome reference)"
    base = mix(canvas, text, .018)
    raised = tone(canvas, min(1, _lab(canvas)[0] + .025))
    subtle = mix(canvas, anchor, .065)
    surfaces = [canvas, base, raised, subtle]
    primary_text = _accessible(text, surfaces, 4.5)
    secondary_text = _accessible(mix(primary_text, canvas, .30), surfaces, 4.5)
    action = _accessible(anchor, surfaces, 4.5)
    direction = -1 if _lab(action)[0] < .6 else 1
    hover = _accessible(tone(action, _lab(action)[0] + direction * .035), surfaces, 4.5)
    active = _accessible(tone(action, _lab(action)[0] + direction * .065), surfaces, 4.5)
    on_action = _on(action, (canvas, "#FFFFFF", "#000000"))
    if min(contrast(on_action, color) for color in (hover, active)) < 4.5:
        on_action = _accessible(on_action, [action, hover, active], 4.5)
    on_brand = _on(anchor, (paired_text, canvas, "#FFFFFF", "#000000"))
    control_border = _accessible(mix(primary_text, canvas, .55), surfaces, 3)
    tokens = {
        "surface": {"canvas": canvas, "base": base, "raised": raised, "subtle": subtle, "brand": anchor},
        "text": {"primary": primary_text, "secondary": secondary_text, "on_brand": on_brand},
        "action": {"primary": action, "hover": hover, "active": active, "foreground": on_action,
                   "secondary_text": action, "secondary_border": control_border},
        "border": {"subtle": mix(primary_text, canvas, .82), "control": control_border,
                   "on_brand": mix(anchor, on_brand, .30)},
        "focus": {"ring": action, "on_brand": _accessible(on_brand, [anchor], 3)},
    }
    checks = []
    def check(role, foreground, background, minimum):
        ratio = contrast(foreground, background)
        checks.append({"role": role, "foreground": foreground, "background": background,
                       "ratio": round(ratio, 3), "minimum": minimum, "pass": ratio >= minimum})
    for name, surface in zip(("canvas", "base", "raised", "subtle"), surfaces):
        check(f"text.primary / {name}", primary_text, surface, 4.5)
        check(f"text.secondary / {name}", secondary_text, surface, 4.5)
        check(f"action.label / {name}", action, surface, 4.5)
        check(f"control.border / {name}", control_border, surface, 3)
        check(f"focus.ring / {name}", action, surface, 3)
    for name, background in (("default", action), ("hover", hover), ("active", active)):
        check(f"primary-button.{name}", on_action, background, 4.5)
    check("text.on_brand / brand", on_brand, anchor, 4.5)
    check("focus.on_brand / brand", tokens["focus"]["on_brand"], anchor, 3)
    palette = {"background": canvas, "surface": base, "surface_alt": subtle, "text": primary_text,
               "muted": secondary_text, "primary": action, "accent": action, "dark": anchor, "on_primary": on_action}
    return {
        "status": "grounded", "source": "explicit_brand" if brand else "measured_reference",
        "reference_url": url, "brand_inputs": brand,
        "primitives": {"brand_anchor": anchor, "canvas_anchor": canvas, "text_anchor": text},
        "provenance": {"brand_anchor": anchor_source, "canvas": brand_location + ".background" if brand.get("background") else "rendered reference body/canvas",
                       "text": brand_location + ".text" if brand.get("text") else "rendered reference body/heading text"},
        "derivation": "OKLab lightness tones with chroma reduced only to stay in sRGB; semantic foregrounds adjusted to pass their contrast targets.",
        "scales": {"brand": _scale(anchor), "neutral": _scale(mix(canvas, text, .55))},
        "tokens": tokens, "palette": palette,
        "usage": {"brand": "Primary actions and the closing brand section; no unrelated accent hue.",
                  "neutrals": "Canvas, content surfaces, text hierarchy, and dividers.",
                  "states": "Hover, active, and focus are derived from the same anchor.",
                  "decorative_borders": "Subtle dividers are decorative; controls use the separate contrast-checked border."},
        "contrast": {"status": "PASS" if all(item["pass"] for item in checks) else "FAIL", "checks": checks,
                     "scope": "Specified opaque semantic pairs; not a complete accessibility or photographic-overlay audit."},
    }


def foundation_css(foundation):
    if not foundation or foundation.get("status") != "grounded":
        return ""
    tokens = foundation["tokens"]
    declarations = []
    for group, roles in tokens.items():
        for role, color in roles.items():
            if not re.fullmatch(r"[a-z_]+", group) or not re.fullmatch(r"[a-z_]+", role):
                raise ValueError("Invalid semantic color role")
            normalized = normalize_color(color)
            if not normalized:
                raise ValueError(f"Invalid color token: {group}.{role}")
            declarations.append(f"--color-{group}-{role.replace('_', '-')}: {normalized};")
    return ":root{" + "".join(declarations) + "}" + r"""
/* Semantic colors; the foundation is the final authority for component colors. */
:root{--bg:var(--color-surface-canvas);--surface:var(--color-surface-base);--surface-alt:var(--color-surface-subtle);--text:var(--color-text-primary);--muted:var(--color-text-secondary);--primary:var(--color-action-primary);--accent:var(--color-action-primary);--dark:var(--color-surface-brand);--on-primary:var(--color-action-foreground);--border:var(--color-border-subtle);--gold:var(--color-action-primary);--gold-light:var(--color-text-on-brand);}
body{background:var(--color-surface-canvas);color:var(--color-text-primary);}
body .header,body .footer{background:var(--color-surface-base);color:var(--color-text-primary);}
body .logo,body .site-nav a{color:var(--color-text-primary);}
body .site-nav a:hover{color:var(--color-action-hover);}
body .button.primary{background:var(--color-action-primary);color:var(--color-action-foreground);border-color:var(--color-action-primary);}
body .button.primary:hover{background:var(--color-action-hover);color:var(--color-action-foreground);}
body .button.primary:active{background:var(--color-action-active);color:var(--color-action-foreground);}
body .button.secondary{background:var(--color-surface-canvas);color:var(--color-action-secondary-text);border-color:var(--color-action-secondary-border);}
body .button.secondary:hover,body .button.secondary:active{background:var(--color-surface-subtle);color:var(--color-action-secondary-text);}
body a:focus-visible,body button:focus-visible,body summary:focus-visible{outline:3px solid var(--color-focus-ring);outline-offset:4px;}
body .eyebrow,body .service-number,body .benefit-number,body .process-card>span,body details summary::after{color:var(--color-action-primary);}
body .service-support{border-left-color:var(--color-border-control);background:var(--color-surface-subtle);}
body .about-support-item{border-top-color:var(--color-border-control);}
body .tone-dark,body[data-cta] .cta-section{background:var(--color-surface-brand)!important;color:var(--color-text-on-brand);}
body .cta-box{background:var(--color-surface-brand);border-color:var(--color-border-on-brand);}
body .tone-dark h2,body .tone-dark h3,body .tone-dark p,body .tone-dark .large-copy,body .tone-dark .eyebrow,body .tone-dark .service-number,body .tone-dark .benefit-number,body .tone-dark .process-card>span,body .cta-box h2,body .cta-box p,body .cta-box .eyebrow{color:var(--color-text-on-brand);}
body .tone-dark .service-card,body .tone-dark .benefit-card,body .tone-dark .process-card,body .tone-dark details,body .tone-dark .location-box{background:var(--color-surface-brand);border-color:var(--color-border-on-brand);}
body .tone-dark details summary::after,body .tone-dark .about-support-item span{color:var(--color-text-on-brand);}
body .tone-dark .button.secondary,body .cta-box .button.secondary,body .cta-box .button.primary{background:var(--color-surface-canvas);color:var(--color-action-secondary-text);border-color:var(--color-surface-canvas);}
body .tone-dark .button.secondary:hover,body .cta-box .button.secondary:hover,body .cta-box .button.primary:hover{background:var(--color-surface-subtle);color:var(--color-action-secondary-text);}
body .tone-dark a:focus-visible,body .tone-dark button:focus-visible,body .tone-dark summary:focus-visible,body .cta-section a:focus-visible,body .cta-section button:focus-visible,body .hero-full-bleed a:focus-visible{outline-color:var(--color-focus-on-brand);}
.hero-full-bleed .hero-overlay{background:linear-gradient(90deg,color-mix(in srgb,var(--color-surface-brand) 92%,transparent),color-mix(in srgb,var(--color-surface-brand) 80%,transparent) 55%,color-mix(in srgb,var(--color-surface-brand) 50%,transparent));}
body .hero-full-bleed .hero-content-overlay :is(h1,.hero-copy,.location,.eyebrow){color:var(--color-text-on-brand);}
@media(max-width:600px){.hero-full-bleed .hero-overlay{background:color-mix(in srgb,var(--color-surface-brand) 90%,transparent);}}
"""
