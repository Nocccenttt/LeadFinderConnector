"""Explicit layout choices shared by generation, rendering, and verification."""

CHOICES = {
    "hero": ("split", "centered-media", "full-bleed", "overlap"),
    "navigation": ("left", "centered"),
    "benefits": ("list", "grid"),
    "process": ("vertical", "horizontal"),
    "faq": ("split", "stacked"),
    "cta": ("banner", "panel"),
    "buttons": ("square", "soft", "pill"),
    "heading_font": ("system", "humanist", "serif", "monospace"),
    "heading_scale": ("balanced", "oversized"),
    "hero_image": ("portrait", "landscape"),
}


def implementation_report(design):
    """Describe renderer coverage without treating a researched URL as visual proof."""
    effects = {"about": {"split-media": "two-column text and image"},
               "services": {"editorial": "bordered service rows"},
               "benefits": {"feature-grid": "two-column benefits"},
               "local": {"split-media": "unequal local columns"}}
    compositions = {}
    for section, choice in design.get("composition", {}).items():
        effect = effects.get(section, {}).get(choice)
        if choice == "asymmetric":
            effect = "1160px container cap only"
        if choice == "editorial" and section in {"services", "benefits", "process", "faq"}:
            effect = effect or "920px heading width only"
        compositions[section] = {"requested": choice, "effect": effect or "shared section layout",
                                 "changes_structure": choice == "split-media" and section in {"about", "local"}
                                 or choice == "editorial" and section == "services"
                                 or choice == "feature-grid" and section == "benefits"}
    plan = design.get("reference_build_plan", {})
    return {"reference_transfer_status": "partial" if plan.get("status") == "grounded" else "unverified",
            "architecture_source": "shared section renderer with supported layout variants",
            "composition_coverage": compositions,
            "uniqueness_verified": False,
            "scope": "Reference measurements affect supported properties; this is not a bespoke reconstruction.",
            "unverified": ["reference fidelity across the full page", "cross-site design uniqueness",
                           "source mobile behavior and motion"]}


def render_choices(design):
    supplied = design.get("render_layout")
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise ValueError("render_layout must be an object")
        invalid = [key for key, values in CHOICES.items() if supplied.get(key) not in values]
        if invalid:
            raise ValueError("Unsupported or missing render_layout choices: " + ", ".join(invalid))
        return {key: supplied[key] for key in CHOICES}
    # Backward compatibility for saved archived specs; split takes precedence
    # over 'full-width split', which previously became a background overlay.
    result = {key: values[0] for key, values in CHOICES.items()}
    result.update(benefits="grid", process="horizontal", faq="stacked", cta="panel", buttons="pill", heading_scale="balanced")
    hero = str(design.get("hero_style", "")).lower()
    if "split" in hero:
        result["hero"] = "split"
    elif any(word in hero for word in ("overlap", "offset", "panel")):
        result["hero"] = "overlap"
    elif any(word in hero for word in ("full-width", "full width", "full-bleed", "background image")):
        result["hero"] = "full-bleed"
    return result


def layout_css(design):
    render = render_choices(design)
    radius = {"square": "0", "soft": "10px", "pill": "999px"}[render["buttons"]]
    font = {"system": "Arial, Helvetica, sans-serif", "humanist": "'Trebuchet MS', Arial, sans-serif",
            "serif": "Georgia, serif", "monospace": "'Courier New', monospace"}[render["heading_font"]]
    scale = "clamp(3.5rem, 5.6vw, 5.6rem)" if render["heading_scale"] == "oversized" else "clamp(3rem, 5vw, 5.3rem)"
    return f"""
/* These selectors implement the saved render_layout contract. */
:root {{ --font-heading: {font}; --control-radius: {radius}; }}
body .button,body .button.primary {{ border-radius: var(--control-radius); white-space: nowrap; box-shadow: none; }}
body .button:active {{ transform: scale(.98); }}
body a:focus-visible,body button:focus-visible,body summary:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 5px; }}
body h1 {{ font-size: {scale}; line-height: 1.02; letter-spacing: -.055em; }}
.hero-split,.hero-centered-media,.hero-overlap {{ background: var(--bg); color: var(--text); }}
.hero-split {{ padding: clamp(48px, 6vw, 100px) 0; }}
.hero-split .hero-grid {{ display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:clamp(36px,5vw,88px);align-items:center; }}
.hero-split h1,.hero-split .hero-copy,.hero-split .location {{ color:var(--text); }}
.hero-split .hero-copy {{ max-width:34rem;font-size:1.15rem;margin-block:26px 30px; }}
.hero-split .hero-visual {{ min-height:0; }}
.hero-split .hero-photo {{ position:relative;inset:auto;height:auto;border:0;border-radius:0;box-shadow:none;background:transparent; }}
.hero-split .hero-photo::after {{ display:none; }}
.hero-split .photo-overlay {{ display:none; }}
.hero-split .hero-photo img {{ width:100%;height:560px;object-fit:cover;display:block; }}
body[data-hero-image="portrait"] .hero-split .hero-photo img {{ aspect-ratio:4/5;height:auto;max-height:680px; }}
.hero-centered-media {{ padding-top:60px; }}
.hero-centered-media .hero-content {{ max-width:1050px;text-align:center;margin:auto;padding-bottom:42px; }}
.hero-centered-media h1,.hero-centered-media .hero-copy,.hero-centered-media .location {{ color:var(--text); }}
.hero-centered-media .hero-copy {{ max-width:650px;margin:24px auto; }}
.hero-centered-media .actions {{ justify-content:center; }}
.hero-centered-media .hero-wide-image img {{ width:100%;height:560px;object-fit:cover;display:block; }}
body[data-navigation="centered"] .nav {{ display:grid;grid-template-columns:1fr auto 1fr; }}
body[data-navigation="centered"] .logo {{ grid-column:2;grid-row:1;text-align:center;max-width:320px; }}
body[data-navigation="centered"] .site-nav {{ grid-column:1;grid-row:1;gap:16px; }}
body[data-navigation="centered"] .nav>.button {{ grid-column:3;grid-row:1;justify-self:end; }}
body[data-benefits="list"] .benefit-grid {{ display:block;border:0; }}
body[data-benefits="list"] .benefit-card {{ display:grid;grid-template-columns:70px 1fr;gap:24px;padding:28px 0;background:transparent;border:0;border-top:1px solid var(--border); }}
body[data-benefits="list"] .benefit-card h3 {{ margin:0; }}
body[data-process="vertical"] [data-section="process"]>.container {{ display:grid;grid-template-columns:1fr 1.3fr;gap:64px; }}
body[data-process="vertical"] .process-grid {{ display:block;border:0; }}
body[data-process="vertical"] .process-card {{ background:transparent;min-height:0;border:0;border-top:1px solid var(--border);padding:24px 0; }}
body[data-process="vertical"] .process-card h3 {{ margin-top:10px; }}
body[data-faq="split"] [data-section="faq"]>.container {{ display:grid;grid-template-columns:.8fr 1.2fr;gap:64px; }}
body[data-faq="split"] .faq {{ width:100%;max-width:none; }}
body[data-faq="split"] details {{ border:0;border-top:1px solid var(--border);border-radius:0;background:transparent; }}
body[data-cta="banner"] .cta-section {{ background:var(--primary)!important; }}
body[data-cta="banner"] .cta-box {{ background:transparent;border:0;box-shadow:none;padding:0; }}
body[data-cta="banner"] .cta-box .button.primary {{ background:var(--surface);color:var(--text); }}
@media(max-width:950px){{
 body[data-navigation="centered"] .nav {{ display:flex; }}
 body[data-navigation="centered"] .logo {{ text-align:left;max-width:240px; }}
 .hero-split .hero-grid {{ grid-template-columns:1fr;gap:36px; }}
 .hero-split .hero-photo img,body[data-hero-image="portrait"] .hero-split .hero-photo img {{ height:440px;aspect-ratio:auto; }}
 body[data-process="vertical"] [data-section="process"]>.container,
 body[data-faq="split"] [data-section="faq"]>.container {{ display:block; }}
}}
@media(max-width:600px){{
 body h1 {{ font-size:clamp(2.7rem,11vw,4rem); }}
 .hero-split .hero-photo img,body[data-hero-image="portrait"] .hero-split .hero-photo img,.hero-centered-media .hero-wide-image img {{ height:360px; }}
 .hero-centered-media {{ padding-top:42px; }}
 body[data-benefits="list"] .benefit-card {{ grid-template-columns:40px 1fr;gap:14px; }}
}}
"""
