"""SEO planning, design-reference discovery, and generated-page quality checks.

Keyword suggestions in this module are heuristic ideas, not measured search-volume
or ranking data. Business facts must come from the supplied business record.
"""
import json
import re
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup


ADMIRE_SEARCH_URL = "https://www.admiretheweb.com/"


def _text(value):
    return str(value or "").strip()


def _business_type(business, handoff):
    nested = handoff.get("business", {}) if isinstance(handoff, dict) else {}
    return (
        _text(business.get("business_type"))
        or _text(business.get("category"))
        or _text(business.get("niche"))
        or _text(nested.get("business_type"))
        or _text(nested.get("category"))
        or "local business"
    )


def _location(business):
    for key in ("city", "locality", "town", "service_area"):
        value = _text(business.get(key))
        if value:
            return value
    return _text(business.get("address"))


def _keyword_location(business, verified_location):
    for key in ("city", "locality", "town", "service_area"):
        value = _text(business.get(key))
        if value:
            return value
    parts = [part.strip() for part in verified_location.split(",") if part.strip()]
    if not parts:
        return ""
    first = parts[0].lower()
    looks_like_street = bool(re.search(r"\d", first)) or bool(
        re.search(r"\b(st|street|rd|road|ave|avenue|blvd|boulevard|drive|dr|lane|ln|court|ct|highway|hwy)\b", first)
    )
    if looks_like_street and len(parts) >= 2:
        return ", ".join(parts[1:3])
    if len(parts) >= 2:
        return ", ".join(parts[:2])
    return parts[0] if not looks_like_street else ""


def build_seo_strategy(business, handoff=None):
    """Create an SEO content brief using verified facts plus clearly labelled ideas."""
    handoff = handoff if isinstance(handoff, dict) else {}
    business = business if isinstance(business, dict) else {}
    nested = handoff.get("business", {}) if isinstance(handoff.get("business"), dict) else {}
    name = (
        _text(business.get("business_name"))
        or _text(business.get("name"))
        or _text(nested.get("name"))
        or "Local Business"
    )
    category = _business_type(business, handoff)
    location = _location(business)
    keyword_location = _keyword_location(business, location)
    services = business.get("services", [])
    if not isinstance(services, list):
        services = []
    service_terms = [
        _text(item.get("name") if isinstance(item, dict) else item)
        for item in services
    ]
    service_terms = [term for term in service_terms if term]

    primary_keyword = " ".join(part for part in (category, keyword_location) if part).strip()
    secondary_keywords = []
    if category:
        secondary_keywords.append(category)
    if keyword_location and category:
        secondary_keywords.append(f"{category} near {keyword_location}")
        secondary_keywords.append(f"local {category} in {keyword_location}")
    secondary_keywords.extend(service_terms)
    secondary_keywords = list(dict.fromkeys(term for term in secondary_keywords if term))

    title = f"{name} | {category.title()}"
    if keyword_location and keyword_location.lower() not in title.lower():
        title = f"{name} | {category.title()} in {keyword_location}"
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > 60:
        title = title[:57].rsplit(" ", 1)[0].rstrip(" |,-") + "..."

    description = (
        f"Learn about {name}, a {category}"
        + (f" serving {keyword_location}" if keyword_location else "")
        + ". Explore available services and contact the business for details."
    )
    if len(description) > 160:
        description = description[:157].rsplit(" ", 1)[0].rstrip(" ,;") + "..."

    seo_config = handoff.get("seo", {}) if isinstance(handoff.get("seo"), dict) else {}
    canonical_url = _text(business.get("canonical_url") or seo_config.get("canonical_url"))
    if canonical_url and urlparse(canonical_url).scheme not in ("http", "https"):
        canonical_url = ""

    return {
        "business_name": name,
        "business_type": category,
        "verified_location": location,
        "keyword_location": keyword_location,
        "primary_keyword": primary_keyword,
        "secondary_keyword_ideas": secondary_keywords,
        "keyword_research_note": (
            "Heuristic suggestions only. No search-volume, difficulty, or ranking "
            "metrics were retrieved; validate with a keyword-data provider before making claims."
        ),
        "search_intent": "Local commercial intent; confirm against actual search results before final publication.",
        "recommended_title": title,
        "recommended_meta_description": description,
        "recommended_h1": f"{category.title()}" + (f" in {keyword_location}" if keyword_location else ""),
        "content_requirements": [
            "Write for customers first; use relevant phrases naturally.",
            "Use one descriptive H1 and a logical H2/H3 hierarchy.",
            "Mention location only when it is present in verified source data.",
            "Include only services supported by the business record.",
            "Do not claim rankings, search volume, certifications, reviews, or results without evidence.",
            "Use helpful FAQs only when answers can be supported by source data.",
        ],
        "canonical_url": canonical_url or None,
    }


def discover_admire_references(business_type, limit=5, timeout=8):
    """Try to find design references on Admire The Web; gracefully report access limits."""
    category = _text(business_type) or "local business"
    search_url = f"{ADMIRE_SEARCH_URL}?s={quote(category)}"
    result = {
        "source": "Admire The Web",
        "query": category,
        "search_url": search_url,
        "references": [],
        "status": "not_available",
        "note": "",
    }
    try:
        response = requests.get(
            search_url,
            timeout=timeout,
            headers={"User-Agent": "LeadFinderDesignResearch/1.0 (+website design research)"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        seen = set()
        for article in soup.select("article"):
            anchor = article.select_one("h1 a, h2 a, h3 a, a[href]")
            if not anchor:
                continue
            href = (anchor.get("href") or "").strip()
            title = anchor.get_text(" ", strip=True)
            parsed = urlparse(href)
            if parsed.scheme not in ("http", "https") or not title or href in seen:
                continue
            if "admiretheweb.com" not in (parsed.netloc or "").lower():
                continue
            seen.add(href)
            excerpt_node = article.select_one("p")
            result["references"].append({
                "title": title,
                "url": href,
                "excerpt": excerpt_node.get_text(" ", strip=True) if excerpt_node else "",
                "source": "Admire The Web",
                "use_for": "Review layout, typography, color, hierarchy, and interaction patterns; do not copy brand assets or page copy.",
            })
            if len(result["references"]) >= max(1, int(limit)):
                break
        if result["references"]:
            result["status"] = "found"
            result["note"] = "Reference candidates discovered. A human should review each URL and confirm suitability."
        else:
            result["note"] = "The search page was reachable but no matching article links were extracted. Add curated references manually."
    except (requests.RequestException, ValueError) as error:
        result["note"] = f"Automatic reference discovery was unavailable: {error}. Add curated reference URLs manually."
    return result


def build_design_blueprint(business, seo_strategy, reference_research):
    """Create a machine-readable design brief that keeps references separate from facts."""
    category = seo_strategy.get("business_type", "local business")
    return {
        "business_name": seo_strategy.get("business_name", "Local Business"),
        "business_type": category,
        "content_alignment": {
            "primary_keyword": seo_strategy.get("primary_keyword", ""),
            "verified_location": seo_strategy.get("verified_location", ""),
            "rule": "The visual hierarchy must support the SEO content without keyword stuffing.",
        },
        "references": reference_research.get("references", []),
        "reference_status": reference_research.get("status", "not_available"),
        "visual_direction": {
            "industry_context": category,
            "principles": [
                "Mobile-first responsive layout",
                "Clear content hierarchy and readable contrast",
                "Prominent, truthful primary call to action",
                "Distinctive layout informed by references without copying them",
                "Use only licensed, supplied, or clearly identified placeholder imagery",
            ],
        },
        "sections": [
            "Header and navigation",
            "Hero with one H1 and primary CTA",
            "Business introduction",
            "Verified services",
            "About and benefits",
            "Process or service steps when supported",
            "Location details when verified",
            "Useful FAQs when source-supported",
            "Contact CTA and footer",
        ],
        "asset_and_claim_rules": [
            "Do not reuse reference-site copy, logos, or proprietary imagery.",
            "Do not invent business facts, service areas, reviews, certifications, or outcomes.",
            "Use descriptive alt text for meaningful images and empty alt text for decorative images.",
        ],
    }


def validate_seo_html(html, business=None, seo_strategy=None):
    """Return actionable SEO/technical checks without claiming ranking outcomes."""
    business = business if isinstance(business, dict) else {}
    seo_strategy = seo_strategy if isinstance(seo_strategy, dict) else {}
    soup = BeautifulSoup(html or "", "html.parser")
    issues = []
    warnings = []
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description_node = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = _text(description_node.get("content")) if description_node else ""
    headings = soup.find_all("h1")
    if not title:
        issues.append("Missing title tag")
    elif len(title) > 60:
        warnings.append(f"Title is {len(title)} characters; consider shortening to about 60 characters.")
    if not description:
        issues.append("Missing meta description")
    elif len(description) > 160:
        warnings.append(f"Meta description is {len(description)} characters; consider shortening to about 160 characters.")
    if len(headings) != 1:
        issues.append(f"Expected exactly one H1; found {len(headings)}")
    if not soup.find("h2"):
        warnings.append("No H2 section headings found")
    if not soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}):
        issues.append("Missing viewport meta tag")
    if soup.find("meta", attrs={"name": re.compile("^robots$", re.I), "content": re.compile("noindex", re.I)}):
        warnings.append("Robots meta tag contains noindex; confirm this is intentional before publishing.")
    if seo_strategy.get("canonical_url") and not soup.find("link", rel="canonical"):
        issues.append("Canonical URL is configured but canonical link tag is missing")
    for index, image in enumerate(soup.find_all("img"), 1):
        if not image.has_attr("alt"):
            issues.append(f"Image {index} is missing an alt attribute")
    for index, anchor in enumerate(soup.find_all("a"), 1):
        href = _text(anchor.get("href"))
        if not href:
            warnings.append(f"Link {index} has no href")
        elif href.lower().startswith(("javascript:", "data:")):
            issues.append(f"Link {index} uses a non-navigational href scheme")
    jsonld_valid = False
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(node.string or node.get_text())
            if isinstance(data, dict) and data.get("@type"):
                jsonld_valid = True
        except (json.JSONDecodeError, TypeError):
            issues.append("Invalid JSON-LD structured data")
    if not jsonld_valid:
        warnings.append("No valid JSON-LD structured data found")
    business_name = _text(business.get("business_name") or business.get("name"))
    if business_name and business_name.lower() not in (soup.get_text(" ", strip=True) or "").lower():
        issues.append("Business name is not visible in page text")
    return {
        "status": "PASS" if not issues else "NEEDS REVIEW",
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "title_length": len(title),
            "meta_description_length": len(description),
            "h1_count": len(headings),
            "h2_count": len(soup.find_all("h2")),
            "image_count": len(soup.find_all("img")),
            "link_count": len(soup.find_all("a")),
            "jsonld_valid": jsonld_valid,
        },
    }


def build_css_theme(tokens):
    """Safely turn AI-proposed visual tokens into CSS variable overrides."""
    tokens = tokens if isinstance(tokens, dict) else {}
    color_keys = {
        "background": "--bg",
        "background_soft": "--bg-soft",
        "card": "--card",
        "text": "--text",
        "muted": "--muted",
        "accent": "--gold",
        "accent_light": "--gold-light",
    }
    declarations = []
    for key, css_var in color_keys.items():
        value = _text(tokens.get(key))
        if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            declarations.append(f"    {css_var}: {value};")
    border = _text(tokens.get("border"))
    if re.fullmatch(r"#[0-9a-fA-F]{6}", border):
        red, green, blue = (int(border[i:i + 2], 16) for i in (1, 3, 5))
        declarations.append(f"    --border: rgba({red},{green},{blue},.16);")
    fonts = {
        "Arial, Helvetica, sans-serif",
        "Georgia, serif",
        "Verdana, Geneva, sans-serif",
        "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    }
    font = _text(tokens.get("font_family"))
    font_rule = f"body {{ font-family: {font}; }}\n" if font in fonts else ""
    radius = _text(tokens.get("radius"))
    if radius in {"4px", "7px", "10px", "14px", "18px", "24px"}:
        declarations.append(f"    --design-radius: {radius};")
    if not declarations and not font_rule:
        return "\n/* No validated AI design tokens; retain the base stylesheet. */\n"
    root_rule = (
        ":root {\n" + "\n".join(declarations) + "\n}\n"
        if declarations else ""
    )
    return (
        "\n/* Validated design tokens informed by the design brief and references. */\n"
        + root_rule
        + font_rule
        + ".button, .service-card, .benefit-card, .faq-item { "
        "border-radius: var(--design-radius, 7px); }\n"
        ".primary { background: var(--gold); color: var(--bg); }\n"
    )
