"""Compose approved content through a reference-mapped layout tree.

The model supplies structure and a source mapping, never HTML, CSS, or copy.
Each content slot is supplied by the factual content renderer exactly once.
"""
from copy import deepcopy
import hashlib
import json
import math

from bs4 import BeautifulSoup


SLOTS = {
    "hero": {"eyebrow", "title", "text", "actions", "location", "image"},
    "about": {"eyebrow", "title", "text", "image"},
    "services": {"eyebrow", "title", "text", "items"},
    "benefits": {"eyebrow", "title", "items"},
    "process": {"eyebrow", "title", "items"},
    "local": {"eyebrow", "title", "text", "location"},
    "faq": {"eyebrow", "title", "items"},
    "cta": {"eyebrow", "title", "text", "actions"},
}
REQUIRED = {key: {"title"} for key in SLOTS}
for _key in ("hero", "about", "services", "local", "cta"):
    REQUIRED[_key].add("text")
for _key in ("services", "benefits", "process", "faq"):
    REQUIRED[_key].add("items")
for _key in ("hero", "cta"):
    REQUIRED[_key].add("actions")
for _key in ("hero", "about"):
    REQUIRED[_key].add("image")

BLUEPRINT_PROMPT = """
Return design_spec.page_blueprint with version:1 and sections:[...]. This is the
executable page architecture. The old composition labels are legacy metadata.
Every included section needs key, reference_section (zero-based index into the
selected rendered_desktop.sections), adaptation (a concrete source-to-business
mapping), tone (canvas/subtle/brand), width (content/wide/full), and layout.
Use only needed sections; hero first, cta included. Blueprint order is page order.
reference_section MUST be one of valid_reference_section_indices of the selected
primary website. Never use an index from another candidate or invent a source
section. A target FAQ may adapt a source editorial/list section even when the
reference has no FAQ: identify that real source index and explain the adaptation.
Layout is a nested tree, up to 5 levels:
 - {"type":"stack","align":"start|center|end","gap":24,"children":[nodes]}
 - {"type":"grid","columns":[0.8,1.2],"align":"start|center|end","gap":48,"children":[nodes]}
 - {"type":"overlay","children":[{"slot":"image"},a stack]} (hero only)
 - {"slot":"title"} (or another content slot for that section)
For items use {"slot":"items","columns":1,"treatment":"rules|plain|panels","numbered":false}.
Available slots:
hero: eyebrow,title,text,actions,location,image;
about: eyebrow,title,text,image; services: eyebrow,title,text,items;
benefits/process/faq: eyebrow,title,items; local: eyebrow,title,text,location;
cta: eyebrow,title,text,actions.
Use every listed slot exactly once in each included section (eyebrow and location
are optional). The renderer owns all content. Never add text, HTML, CSS, URLs or
claims to nodes. Preserve reading order within each text group. All grids collapse
to a single column on mobile in DOM reading order. Avoid decorative numbering
unless it serves ordered process content or is supported by the source.
Use measured section_layouts (children, images, headings, grid tracks, alignment)
to map page rhythm, image/text grouping, rows versus columns, and section order.
Adapt commercial product grids to real service content; explain the adaptation.
Do not repeat one hero/about/services/benefits/process/local/faq/cta template by
default. Omit redundant sections when content is sparse. Different references
should result in different grouping and composition where their evidence differs.
"""


def _number(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Invalid blueprint {name}: expected {low}..{high}")
    return value


def validate_blueprint(design, references=None):
    blueprint = design.get("page_blueprint")
    if not isinstance(blueprint, dict) or blueprint.get("version") != 1:
        raise ValueError("A version 1 page_blueprint is required")
    sections = blueprint.get("sections")
    if not isinstance(sections, list) or not 2 <= len(sections) <= 8:
        raise ValueError("Blueprint needs 2..8 sections")
    keys = [section.get("key") for section in sections if isinstance(section, dict)]
    if len(keys) != len(sections) or any(key not in SLOTS for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("Blueprint section keys must be supported and unique")
    if keys[0] != "hero" or "cta" not in keys:
        raise ValueError("Blueprint must start with hero and include cta")
    source_sections = None
    if references is not None:
        selected = design.get("reference_selection", {}).get("website_url")
        candidate = next((item for item in references if item.get("website_url") == selected), {})
        observed = candidate.get("rendered_desktop", {})
        source_sections = observed.get("sections", []) if observed.get("status") == "measured" else []
    for section in sections:
        key = section["key"]
        if section.get("tone") not in ("canvas", "subtle", "brand") or section.get("width") not in ("content", "wide", "full"):
            raise ValueError(f"Invalid blueprint tone/width for {key}")
        index = section.get("reference_section")
        if type(index) is not int or index < 0 or (source_sections is not None and index >= len(source_sections)):
            available = f"0..{len(source_sections)-1}" if source_sections is not None else "a nonnegative integer"
            raise ValueError(f"Invalid reference_section {index!r} for {key}; selected reference allows {available}")
        reason = section.get("adaptation")
        if not isinstance(reason, str) or not 20 <= len(reason.strip()) <= 1200:
            raise ValueError(f"Explain the reference adaptation for {key}")
        used = set()
        count = 0

        def walk(node, depth=0):
            nonlocal count
            count += 1
            if not isinstance(node, dict) or depth > 5 or count > 40:
                raise ValueError("Blueprint layout tree is invalid or too large")
            if "slot" in node:
                slot = node["slot"]
                if not isinstance(slot, str) or slot not in SLOTS[key] or slot in used:
                    raise ValueError(f"Unsupported or duplicate {key} content slot: {slot}")
                allowed = {"slot", "columns", "treatment", "numbered"} if slot == "items" else {"slot"}
                if set(node) - allowed:
                    raise ValueError("Content nodes may not add HTML, styles, or copy")
                used.add(slot)
                if slot == "items":
                    columns = node.get("columns", 1)
                    if type(columns) is not int or not 1 <= columns <= 4:
                        raise ValueError("Item columns must be 1..4")
                    if node.get("treatment", "plain") not in ("plain", "rules", "panels") or type(node.get("numbered", False)) is not bool:
                        raise ValueError("Invalid item treatment")
                return
            kind = node.get("type")
            if kind not in ("stack", "grid", "overlay") or set(node) - {"type", "align", "gap", "columns", "children"}:
                raise ValueError("Unsupported layout node")
            if node.get("align", "start") not in ("start", "center", "end"):
                raise ValueError("Invalid layout alignment")
            _number(node.get("gap", 24), 0, 120, "gap")
            children = node.get("children")
            if not isinstance(children, list) or not 1 <= len(children) <= 8:
                raise ValueError("Layout node needs 1..8 children")
            if kind == "grid":
                columns = node.get("columns")
                if not isinstance(columns, list) or not 2 <= len(columns) <= 4:
                    raise ValueError("Grid needs 2..4 column proportions")
                for value in columns:
                    _number(value, .25, 4, "column proportion")
            if kind == "overlay" and (key != "hero" or len(children) != 2 or children[0] != {"slot": "image"} or not isinstance(children[1], dict) or children[1].get("type") != "stack"):
                raise ValueError("Overlay needs a hero image followed by one text stack")
            for child in children:
                walk(child, depth + 1)
        walk(section.get("layout"))
        missing = REQUIRED[key] - used
        if missing:
            raise ValueError(f"Blueprint would discard {key} content: {', '.join(sorted(missing))}")
    return blueprint


def _content_slots(html, key):
    soup = BeautifulSoup(html, "html.parser")
    selectors = {
        "title": "h1" if key == "hero" else "h2",
        "eyebrow": ".eyebrow",
        "image": "img",
        "actions": ".actions" if key == "hero" else ".cta-actions",
        "location": ".location" if key == "hero" else ".location-box",
        "text": {"hero": ".hero-copy", "about": ".intro-copy,.large-copy", "services": ".section-heading p",
                 "local": ".local-copy>p", "cta": ".cta-box>div>p"}.get(key, ".unused-slot"),
    }
    slots = {}
    for name, selector in selectors.items():
        fragments = []
        for original in soup.select(selector):
            node = deepcopy(original)
            # Keep functional button classes; discard the former layout wrappers.
            for element in [node, *node.find_all(True)]:
                classes = element.get("class", [])
                element.attrs.pop("style", None)
                element.attrs.pop("class", None)
                if "button" in classes:
                    element["class"] = [c for c in classes if c in ("button", "primary", "secondary")]
            fragments.append(str(node))
        slots[name] = "".join(fragments)
    items = soup.select({"services": ".service-card", "benefits": ".benefit-card", "process": ".process-card", "faq": "details"}.get(key, ".unused-slot"))
    slots["items"] = items
    return slots


def _nodes(node, path):
    yield path, node
    for index, child in enumerate(node.get("children", [])):
        yield from _nodes(child, f"{path}-{index}")


def compose_sections(section_html, design):
    blueprint = validate_blueprint(design)
    rendered = []
    for section in blueprint["sections"]:
        key = section["key"]
        slots = _content_slots(section_html[key], key)

        def render(node, path):
            if "slot" in node:
                slot = node["slot"]
                if slot == "items":
                    items = []
                    for original in slots["items"]:
                        item = deepcopy(original)
                        item["class"] = ["rc-item"]
                        for element in item.find_all(True):
                            if element.get("class") in (["service-number"], ["benefit-number"]) or (key == "process" and element.name == "span"):
                                if not node.get("numbered", False):
                                    element.decompose()
                                    continue
                            element.attrs.pop("class", None)
                        items.append(str(item))
                    content = "".join(items)
                    classes = f"rc-items rc-treatment-{node.get('treatment', 'plain')}"
                else:
                    content = slots[slot]
                    classes = f"rc-slot rc-{slot}"
                return f'<div class="rc-node {classes}" data-rc-node="{path}">{content}</div>'
            content = "".join(render(child, f"{path}-{index}") for index, child in enumerate(node["children"]))
            return f'<div class="rc-node rc-{node["type"]}" data-rc-node="{path}">{content}</div>'

        anchor = {"hero": "home", "cta": "contact"}.get(key, key)
        # Content nodes own their grouping; there are no inherited section grids.
        rendered.append(f'<section id="{anchor}" data-section="{key}" data-reference-section="{section["reference_section"]}" class="rc-section rc-tone-{section["tone"]} rc-width-{section["width"]}"><div class="rc-shell">{render(section["layout"], key)}</div></section>')
    return "\n".join(rendered)


def blueprint_css(design):
    if not design.get("page_blueprint"):
        return ""
    blueprint = validate_blueprint(design)
    rules = [BASE_CSS]
    for section in blueprint["sections"]:
        metric = design.get("reference_build_plan", {}).get("section_metrics", [])
        index = section["reference_section"]
        if index < len(metric):
            spacing = metric[index]
            key = section["key"]
            rules.append(f'body .rc-section[data-section="{key}"]{{--reference-image-ratio:{spacing["image_ratio"]};padding-top:{spacing["padding_top_px"]}px;padding-bottom:{spacing["padding_bottom_px"]}px;}}')
        for path, node in _nodes(section["layout"], section["key"]):
            selector = f'body [data-rc-node="{path}"]'
            kind = node.get("type")
            if kind in ("stack", "grid"):
                align = node.get("align", "start")
                rules.append(f'{selector}{{gap:{node.get("gap",24)}px;align-items:{align};}}')
                if kind == "grid":
                    columns = " ".join(f"minmax(0,{value}fr)" for value in node["columns"])
                    rules.append(f'{selector}{{grid-template-columns:{columns};}}')
                    rules.append(f'@media(max-width:800px){{{selector}{{grid-template-columns:minmax(0,1fr);gap:32px;}}}}')
                else:
                    rules.append(f'{selector}{{text-align:{dict(start="left",center="center",end="right")[align]};}}')
            if node.get("slot") == "items":
                rules.append(f'{selector}{{grid-template-columns:repeat({node.get("columns",1)},minmax(0,1fr));}}')
                rules.append(f'@media(max-width:800px){{{selector}{{grid-template-columns:minmax(0,1fr);}}}}')
    return "\n".join(rules)


def blueprint_manifest(design):
    blueprint = validate_blueprint(design)
    structure = [{"key": section["key"], "width": section["width"], "layout": section["layout"]} for section in blueprint["sections"]]
    signature = hashlib.sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest()[:16]
    return {"architecture_source": "reference-mapped composition tree", "reference_transfer_status": "mapped",
            "source_url": design.get("reference_selection", {}).get("website_url"),
            "structure_signature": signature, "sections": blueprint["sections"],
            "uniqueness_verified": False,
            "scope": "Every included section is composed from a validated tree and source mapping. Visual fidelity and cross-site uniqueness require rendered comparisons."}


BASE_CSS = r"""
/* Reference composition tree. Shared primitives, independently composed sections. */
body .rc-section{padding:var(--section-space,80px) 0;color:var(--color-text-primary,var(--text));background:var(--color-surface-canvas,var(--bg));}
body .rc-shell{width:calc(100% - 48px);max-width:var(--max,1200px);margin:auto;}
body .rc-width-content .rc-shell{max-width:min(920px,var(--max,1200px));}
body .rc-width-full .rc-shell{width:100%;max-width:none;}
body .rc-node{min-width:0;}
body .rc-section :is(h1,h2,h3,p,summary){color:inherit;}
body .rc-stack{display:flex;flex-direction:column;width:100%;}
body .rc-grid,body .rc-items{display:grid;gap:28px;}
body .rc-items{width:100%;}
body .rc-slot>*{margin:0;}
body .rc-title{width:100%;}
body .rc-title h1{max-width:18ch;}
body .rc-title h2{max-width:28ch;}
body .rc-text{max-width:62ch;}
body .rc-text p+p{margin-top:24px;}
body .rc-text p{font-size:1.05rem;line-height:1.65;color:inherit;}
body .rc-eyebrow{font-size:.75rem;letter-spacing:.09em;}
body .rc-actions>div{display:flex;flex-wrap:wrap;gap:12px;}
body .rc-image{width:100%;}
body .rc-image img{display:block;width:100%;height:auto;aspect-ratio:var(--reference-image-ratio,1.33);object-fit:cover;border-radius:0;box-shadow:none;}
body .rc-item{padding:0;border:0;background:transparent;min-height:0;}
body .rc-item h3{margin:0 0 12px;font-weight:500;}
body .rc-item p{margin:0;line-height:1.65;color:inherit;}
body .rc-item>span{display:block;font-size:.8rem;margin-bottom:18px;}
body .rc-treatment-rules>.rc-item{border-top:1px solid currentColor;padding-block:24px;}
body .rc-treatment-panels>.rc-item{padding:28px;background:var(--color-surface-subtle,var(--surface-alt));}
body .rc-items details{border-radius:0;color:inherit;background:transparent;}
body .rc-items summary{font-weight:500;padding:0;}
body .rc-items details[open]>p{margin-top:18px;}
body .rc-items details summary::after{color:inherit;}
body .rc-tone-subtle{background:var(--color-surface-subtle,var(--surface-alt));}
body .rc-tone-brand{background:var(--color-surface-brand,var(--primary));color:var(--color-text-on-brand,var(--on-primary));}
body .rc-tone-brand .rc-treatment-panels>.rc-item{background:transparent;border:1px solid currentColor;}
body .rc-tone-brand .button.primary{background:var(--color-surface-canvas,var(--bg));color:var(--color-text-primary,var(--text));}
body .rc-tone-brand .button:hover{background:var(--color-surface-subtle,var(--surface-alt));color:var(--color-text-primary,var(--text));}
body .rc-tone-brand :is(a,summary):focus-visible,body .rc-overlay :is(a,summary):focus-visible{outline-color:var(--color-focus-on-brand,var(--on-primary));}
body .rc-location{font-size:.9rem;}
body .rc-location h3{font-size:1.05rem;margin-top:12px;}
body .rc-overlay{position:relative;min-height:660px;display:grid;align-items:center;padding:64px max(24px,calc((100vw - var(--max,1200px))/2));isolation:isolate;color:var(--color-text-on-brand,var(--on-primary));}
body .rc-overlay>.rc-image{position:absolute;inset:0;z-index:-2;}
body .rc-overlay>.rc-image img{height:100%;aspect-ratio:auto;}
body .rc-overlay:after{content:"";position:absolute;inset:0;background:color-mix(in srgb,var(--color-surface-brand,var(--primary)) 83%,transparent);z-index:-1;}
body .rc-overlay>.rc-stack{max-width:800px;}
body .rc-section[data-section]:has(.rc-overlay){padding:0;}
@media(max-width:800px){body .rc-section{padding-block:48px;}body .rc-shell{width:calc(100% - 40px);}body .rc-overlay{min-height:600px;padding:48px 20px;}body .rc-actions .button{white-space:normal;}body .rc-title{max-width:100%;}body .rc-section h1{font-size:clamp(2.4rem,10vw,3.6rem);}}
"""
