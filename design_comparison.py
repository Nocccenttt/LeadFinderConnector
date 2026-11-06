"""Compare generated artifacts without treating color or spacing changes as new layouts."""
import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


def layout_shape(node):
    if "slot" in node:
        result = {"slot": node["slot"]}
        if node["slot"] == "items":
            result["columns"] = node.get("columns", 1)
        return result
    children = [layout_shape(child) for child in node.get("children", [])]
    if node.get("type") == "stack":
        children = [nested for child in children for nested in (child["children"] if child.get("type") == "stack" else [child])]
    if len(children) == 1:
        return children[0]
    result = {"type": node.get("type"), "children": children}
    if node.get("type") == "grid":
        result["columns"] = len(node.get("columns", []))
    return result


def hero_family(node):
    if "slot" in node:
        return None if node["slot"] in ("eyebrow", "location") else {"slot":node["slot"]}
    children = [child for child in (hero_family(child) for child in node.get("children", [])) if child]
    if node.get("type") == "stack":
        children = [nested for child in children for nested in (child["children"] if child.get("type") == "stack" else [child])]
    if len(children) == 1:
        return children[0]
    return {"type":node.get("type"),"children":children}


def _identity_mask(text, business):
    text = text.casefold()
    values = [str(business.get(key) or "") for key in ("business_name", "name", "address", "phone", "website")]
    address = str(business.get("address") or "").split(",")
    if len(address) >= 3:
        values.append(address[-3].strip())
    for value in sorted(values, key=len, reverse=True):
        if value:
            text = text.replace(value.casefold(), " ")
    return re.findall(r"[a-z]+", re.sub(r"\b\d+\b", " ", text))


def _load(folder):
    folder = Path(folder)
    business = json.loads((folder/"business.json").read_text(encoding="utf-8"))
    design = json.loads((folder/"website/design_spec.json").read_text(encoding="utf-8"))
    blueprint = design.get("page_blueprint")
    if not blueprint:
        raise ValueError(f"No generated page blueprint in {folder.name}")
    sections = [{"key": section["key"], "layout": layout_shape(section["layout"])} for section in blueprint["sections"]]
    signature = hashlib.sha256(json.dumps(sections, sort_keys=True).encode()).hexdigest()[:16]
    page = BeautifulSoup((folder/"website/index.html").read_text(encoding="utf-8"), "html.parser")
    for node in page.select("script,style,header,footer,svg"):
        node.decompose()
    main = page.select_one("main") or page
    words = _identity_mask(main.get_text(" ", strip=True), business)
    grams = {tuple(words[index:index+5]) for index in range(max(0, len(words)-4))}
    palette = design.get("color_foundation", {}).get("palette", design.get("design_system", {}).get("palette", {}))
    return {"name":business.get("business_name", folder.name),"folder":str(folder),"sections":sections,
            "hero_family":hero_family(blueprint["sections"][0]["layout"]),
            "structure":signature,"words":words,"grams":grams,"palette":palette,
            "reference":design.get("reference_selection",{}).get("website_url")}


def compare_sites(folders):
    sites = [_load(folder) for folder in folders]
    pairs = []
    for left, right in itertools.combinations(sites, 2):
        union = left["grams"] | right["grams"]
        overlap = len(left["grams"] & right["grams"]) / len(union) if union else 0
        a = {section["key"]:section["layout"] for section in left["sections"]}
        b = {section["key"]:section["layout"] for section in right["sections"]}
        keys = a.keys() | b.keys()
        shared = sum(a.get(key) == b.get(key) for key in keys) / len(keys)
        same_palette = left["palette"] == right["palette"]
        same_structure = left["structure"] == right["structure"]
        same_hero = left["hero_family"] == right["hero_family"]
        review = same_structure or (same_hero and shared >= .6 and same_palette) or overlap > .55
        pairs.append({"left":left["name"],"right":right["name"],"same_structure":same_structure,
                      "matching_section_layout_fraction":round(shared,3),"masked_copy_5gram_overlap":round(overlap,3),
                      "same_copy_after_identity_mask":left["words"]==right["words"],"same_palette":same_palette,
                      "same_reference":left["reference"]==right["reference"],"review_repetition":review})
        pairs[-1]["same_hero_family"] = same_hero
    return {"sites":len(sites),"distinct_structure_count":len({site["structure"] for site in sites}),
            "distinct_hero_family_count":len({json.dumps(site["hero_family"],sort_keys=True) for site in sites}),
            "pairs_requiring_review":sum(pair["review_repetition"] for pair in pairs),
            "criteria":"Structure ignores color, spacing, radius, widths and source indices; copy comparison masks business identity. Rendered review remains necessary.",
            "cases":[{key:site[key] for key in ("name","folder","reference","structure")} for site in sites],"pairs":pairs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare_sites(args.folders)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
