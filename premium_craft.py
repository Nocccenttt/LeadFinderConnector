"""Shared craft standards; page composition and brand colors remain reference-led."""
from pathlib import Path
import shutil


CRAFT_PROMPT = """
Apply the approved Emil Kowalski design-engineering principles: clear hierarchy,
readable sans-serif body copy, precise spacing, deliberate image framing and
responsive physical feedback. Let the selected reference determine composition
and the color foundation determine color; never reuse a universal white/burgundy
pet-business template. Use the approved crisp sans-serif typography; references
should differentiate layout, imagery and color. Prefer clear imagery to a heavy tint.
For this approved profile, keep hero text and photography separate: use a grid
or stack, never an overlay hero. Adapt overlaid references through proportions,
content rhythm and color instead of reproducing their background treatment.
Add visual emphasis through a purposeful brand-colored feature section OR strong
editorial typography and imagery; avoid repeated cards, ornamental numbering and
filler. Use an audience-appropriate headline with personality and a clear local
service context in the supporting copy. General planning guidance and helpful FAQs
are welcome. Do not turn hypothetical services into company offerings.
For sparse data avoid 'we offer/provide/specialize' assertions. Write descriptive
category context and customer questions. No invented prices, hours, credentials,
history, reviews, results, guarantees or staff. Return an empty services array
when services are not verified. Write 4-6 useful FAQs, and category-specific guide
topics. Feature copy expresses a general customer concern, not a company promise.
Guidance should help customers choose, ask questions and arrange a visit/project.
Do not give hands-on health, grooming, electrical, roofing or hazardous-work instructions.
"""


def install_craft_fonts(output_dir):
    fonts = Path(output_dir)/"fonts"
    fonts.mkdir(exist_ok=True)
    source = Path(__file__).resolve().parent/"assets/fonts"
    for name in ("Geist.ttf", "Geist-OFL.txt"):
        shutil.copy2(source/name, fonts/name)


def validate_craft_blueprint(blueprint):
    def walk(node):
        if node.get("type") == "overlay":
            raise ValueError("Approved modern-minimal profile requires separate hero text/image; use grid or stack, not overlay")
        for child in node.get("children", []):
            walk(child)
    walk(blueprint["sections"][0]["layout"])


def craft_css(design):
    heading = "'Craft Sans',Arial,sans-serif"
    weight = 550
    return r"""
@font-face{font-family:'Craft Sans';src:url('fonts/Geist.ttf') format('truetype');font-weight:100 900;font-display:swap;}
:root{--font-body:'Craft Sans',Arial,sans-serif;--ease-out:cubic-bezier(.23,1,.32,1);}
body{font-family:var(--font-body);-webkit-font-smoothing:antialiased;font-synthesis:none;}
body h1,body h2,body h3{text-wrap:balance;}
body p{text-wrap:pretty;}
.skip-link{position:fixed;top:12px;left:16px;z-index:100;padding:12px 20px;background:var(--color-action-primary,var(--primary));color:var(--color-action-foreground,var(--on-primary));transform:translateY(-160%);}
.skip-link:focus{transform:none;}
body .rc-text p{color:var(--color-text-secondary,var(--muted));line-height:1.8;font-size:1rem;}
body .rc-text{max-width:58ch;}
body .rc-tone-brand .rc-text p,body .rc-overlay .rc-text p{color:inherit;}
body .rc-image img{border-radius:16px;}
body .rc-overlay>.rc-image img{border-radius:0;}
body .rc-items{gap:30px;}
body .rc-item h3{font-size:1.1rem;line-height:1.45;}
body .rc-item p{font-size:.94rem;line-height:1.8;color:var(--color-text-secondary,var(--muted));}
body .rc-tone-brand .rc-item p{color:inherit;}
body .rc-item .guide-prompt{font-size:.8rem;color:var(--color-action-primary,var(--primary));margin-top:14px;}
body .rc-tone-brand .rc-item .guide-prompt{color:inherit;}
body .rc-slot.rc-actions>div{gap:14px;}
body .button,body .button.primary{font-family:var(--font-body);font-size:14px;font-weight:550;min-height:46px;border-radius:9px;box-shadow:none;transition:none;}
body .button:is(.primary,.secondary):hover{transform:none;box-shadow:none;}
body[data-input=keyboard] :is(a,button,summary,.site-nav,.header){transition:none!important;}
body[data-input=pointer] .button{transition:transform 140ms var(--ease-out),background-color 160ms ease,color 160ms ease;}
body[data-input=pointer] .button:active{transform:scale(.98);}
body a:focus-visible,body button:focus-visible,body summary:focus-visible{outline-width:3px;outline-offset:5px;}
body .rc-items summary{min-height:48px;line-height:1.5;}
body .rc-items details summary::after{color:inherit;}
body .rc-slot.rc-eyebrow{font-size:.68rem;letter-spacing:.12em;}
body .header{background:var(--color-surface-canvas,var(--bg));backdrop-filter:none;}
body .logo{font-family:var(--font-body);font-size:17px;font-weight:600;letter-spacing:-.025em;line-height:1.3;}
body .rc-title h1{line-height:1.06;}
body .rc-title h2{line-height:1.14;}
@media(hover:hover) and (pointer:fine){body[data-input=pointer] .rc-image img{transition:transform 700ms var(--ease-out);}body[data-input=pointer] .rc-image:hover img{transform:scale(1.015);}.rc-image{overflow:hidden;border-radius:16px;}body .rc-overlay>.rc-image{border-radius:0;}}
@media(max-width:800px){body .rc-section[data-section]:not(:has(.rc-overlay)){padding-block:48px;}body .rc-text p{font-size:15px;}body .rc-title h2{font-size:32px;}body .rc-actions .button{white-space:normal;}body .rc-image img{border-radius:12px;}body .button{font-size:13px;}}
@media(prefers-reduced-motion:reduce){body *,body *::before,body *::after{transition:none!important;animation:none!important;}body[data-input=pointer] .button:active,body[data-input=pointer] .rc-image:hover img{transform:none;}}
""" + f"body .rc-title :is(h1,h2){{font-family:{heading};font-weight:{weight};}}"


def craft_js():
    return (Path(__file__).resolve().parent/"assets/craft-interactions.js").read_text(encoding="utf-8")
