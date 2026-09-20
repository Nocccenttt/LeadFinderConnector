#!/usr/bin/env python3
"""
Local-business website lead finder.

Input: niche + area
Workflow: Google Places -> website check -> public social/contact discovery
          -> opportunity score -> CSV

Example:
  python seo_lead_finder_maps.py --niche "plumber" --area "Philadelphia, PA"

Requires GOOGLE_MAPS_API_KEY in the environment.
"""

import argparse
import csv
import os
import json
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17 Safari/605.1.15",
]
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SOCIAL_DOMAINS = {
    "facebook.com": "facebook", "instagram.com": "instagram",
    "linkedin.com": "linkedin", "youtube.com": "youtube",
    "tiktok.com": "tiktok", "x.com": "x", "twitter.com": "x",
}
CONTACT_PATHS = ["", "/contact", "/contact-us", "/contactus", "/about", "/about-us", "/get-in-touch"]


@dataclass
class Lead:
    maps_position: int
    name: str
    address: str = ""
    phone: str = ""
    website: str = ""
    website_status: str = ""
    facebook: str = ""
    instagram: str = ""
    linkedin: str = ""
    other_socials: str = ""
    email: str = ""
    email_source_url: str = ""
    website_quality: str = ""
    opportunity_score: int = 0
    opportunity: str = ""
    reason: str = ""
    opportunity_reasons: str = ""


def headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}


def root_domain(url):
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def fetch(url, timeout=10):
    try:
        print(f"       [web] Checking {url}", flush=True)
        return requests.get(url, headers=headers(), timeout=timeout)
    except requests.RequestException:
        return None


def google_places_search(niche, area, api_key, max_results):
    """Find businesses through Google Places Text Search, not Maps HTML scraping."""
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    request_headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri",
    }
    print(f"[search] Connecting to Google Places...", flush=True)
    response = requests.post(
        endpoint,
        headers=request_headers,
        json={"textQuery": f"{niche} in {area}", "pageSize": min(max_results, 20)},
        timeout=20,
    )
    print("[search] Google Places response received.", flush=True)
    response.raise_for_status()
    leads = []
    for position, place in enumerate(response.json().get("places", []), 1):
        leads.append(Lead(
            maps_position=position,
            name=place.get("displayName", {}).get("text", ""),
            address=place.get("formattedAddress", ""),
            phone=place.get("nationalPhoneNumber", ""),
            website=place.get("websiteUri", ""),
        ))
    return leads


def inspect_website(website):
    result = {
        "status": "unknown", "email": "", "email_source_url": "",
        "facebook": "", "instagram": "", "linkedin": "", "other_socials": [],
        "mobile_meta": False, "cta": False, "contact_info": False,
    }
    if not website:
        result["status"] = "no website"
        return result

    parsed = urlparse(website)
    root = f"{parsed.scheme}://{parsed.netloc}"
    homepage = fetch(root)
    if not homepage or homepage.status_code >= 400:
        result["status"] = "broken"
        return result

    result["status"] = "working"
    checked_urls = set()

    for path in CONTACT_PATHS:
        page_url = urljoin(root, path)
        if page_url in checked_urls:
            continue
        checked_urls.add(page_url)
        response = fetch(page_url)
        if not response or response.status_code >= 400:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        if soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}):
            result["mobile_meta"] = True

        page_text = soup.get_text(" ", strip=True).lower()
        if any(p in page_text for p in ("contact us", "call us", "get a quote", "request a quote", "book now", "schedule")):
            result["cta"] = True
        if any(p in page_text for p in ("phone", "email", "address", "hours")):
            result["contact_info"] = True

        if not result["email"]:
            mailto = soup.select_one('a[href^="mailto:"]')
            if mailto:
                email = mailto["href"].replace("mailto:", "").split("?")[0].strip()
                if EMAIL_RE.fullmatch(email):
                    result["email"], result["email_source_url"] = email, page_url
            else:
                match = EMAIL_RE.search(soup.get_text(" "))
                if match:
                    result["email"], result["email_source_url"] = match.group(0), page_url

        for link in soup.select("a[href]"):
            href = link.get("href", "")
            if not href.startswith("http"):
                continue
            domain = root_domain(href)
            for social_domain, social_name in SOCIAL_DOMAINS.items():
                if domain == social_domain or domain.endswith("." + social_domain):
                    if social_name in ("facebook", "instagram", "linkedin") and not result[social_name]:
                        result[social_name] = href
                    elif social_name not in ("facebook", "instagram", "linkedin"):
                        result["other_socials"].append(href)

    result["other_socials"] = list(dict.fromkeys(result["other_socials"]))
    return result


def score_lead(lead, site):
    """Classify a lead consistently from its verified website condition."""
    if not lead.website:
        return 100, "HIGH", "no website", "NO WEBSITE"

    if site["status"] == "broken":
        return 90, "HIGH", "broken website", "BROKEN WEBSITE"

    score = 0
    reasons = []

    if not site["mobile_meta"]:
        score += 20
        reasons.append("missing mobile viewport")

    if not site["cta"]:
        score += 15
        reasons.append("weak/no CTA")

    if not site["contact_info"]:
        score += 10
        reasons.append("weak/no contact information")

    if score >= 30:
        priority = "HIGH"
        quality = "WEAK"
    elif score >= 15:
        priority = "MEDIUM"
        quality = "NEEDS WORK"
    else:
        priority = "LOW"
        quality = "GOOD"

    reason = "; ".join(reasons) if reasons else "no major issues detected"
    return score, priority, reason, quality

def enrich_lead(lead):
    site = inspect_website(lead.website)
    lead.website_status = site["status"]
    lead.email = site["email"]
    lead.email_source_url = site["email_source_url"]
    lead.facebook = site["facebook"]
    lead.instagram = site["instagram"]
    lead.linkedin = site["linkedin"]
    lead.other_socials = "; ".join(site["other_socials"])
    lead.opportunity_score, lead.opportunity, lead.reason, lead.website_quality = score_lead(lead, site)


def safe_filename(value):
    """Turn niche/area text into a Windows-safe filename."""
    value = re.sub(r'[<>:"/\\|?*]+', "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:150].rstrip(" .")


def write_codex_handoff(lead, base_dir):
    """Create a priority-folder handoff for one lead."""
    priority = lead.opportunity.upper()
    business_dir = Path(base_dir) / priority / safe_filename(lead.name)
    business_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "business_name": lead.name,
        "opportunity": lead.opportunity,
        "opportunity_score": lead.opportunity_score,
        "opportunity_reasons": lead.reason,
        "website_quality": lead.website_quality,
        "website": lead.website,
        "website_status": lead.website_status,
        "address": lead.address,
        "phone": lead.phone,
        "email": lead.email,
        "email_found_on": lead.email_source_url,
        "facebook": lead.facebook,
        "instagram": lead.instagram,
        "linkedin": lead.linkedin,
        "other_socials": lead.other_socials,
        "maps_position": lead.maps_position,
    }

    (business_dir / "business.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if priority == "LOW":
        return

    prompt = f"""# Website Build Prompt

Build a complete modern, mobile-first local-business website for **{lead.name}**.

## Source of truth
Use ONLY the information in `business.json` and the verified business information provided by this lead-finder handoff. Do not invent:
- services
- reviews or testimonials
- certifications
- awards
- years in business
- guarantees
- locations
- pricing
- claims about the company

If information is missing, leave the section out or use neutral structure/placeholders rather than making up facts.

## Lead opportunity
- Priority: {lead.opportunity}
- Opportunity score: {lead.opportunity_score}/100
- Reason: {lead.reason}

## Verified business information
- Business: {lead.name}
- Address: {lead.address}
- Phone: {lead.phone}
- Website: {lead.website}
- Website status: {lead.website_status}
- Email: {lead.email}
- Facebook: {lead.facebook}
- Instagram: {lead.instagram}
- LinkedIn: {lead.linkedin}

## Build direction
Create a professional, conversion-focused website appropriate for the business. Make it mobile-first, fast, accessible, and easy to navigate. Use clear calls to action based only on verified contact information.

Use the project's existing website-generation workflow/tools when available. Audit the design after implementation and improve any obvious usability, responsiveness, hierarchy, spacing, typography, or conversion issues.

Before adding any business-specific claim, check `business.json`. Preserve the actual information exactly.
"""
    (business_dir / "WEBSITE_BUILD_PROMPT.md").write_text(prompt, encoding="utf-8")

    readme = f"""# {lead.name}

This folder is ready to hand off to the website generator.

1. Open `business.json` for the verified lead data.
2. Use `WEBSITE_BUILD_PROMPT.md` as the build instruction.
3. Do not invent missing business information.
4. Priority: {lead.opportunity}
5. Score: {lead.opportunity_score}/100
"""
    (business_dir / "README.md").write_text(readme, encoding="utf-8")


def write_opportunity_csv(leads, path, priority):
    selected = [x for x in leads if x.opportunity.upper() == priority]
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "business_name", "maps_position", "address", "phone", "website",
            "website_status", "facebook", "instagram", "linkedin", "other_socials",
            "email", "email_found_on", "opportunity_score", "opportunity",
            "opportunity_reasons"
        ])
        for lead in selected:
            writer.writerow([
                lead.name, lead.maps_position, lead.address, lead.phone, lead.website,
                lead.website_status, lead.facebook, lead.instagram, lead.linkedin,
                lead.other_socials, lead.email, lead.email_source_url,
                lead.opportunity_score, lead.opportunity, lead.reason
            ])


def run(niche, area, output, max_results, output_dir='outputs', codex_dir='codex_handoffs', progress_callback=None):
    def progress(**event):
        if progress_callback:
            progress_callback(event)

    progress(
        phase="Searching",
        subphase=f"{niche} • {area}",
        current_business="",
        current_index=0,
        total=0,
        percent=2,
        high=0,
        medium=0,
        low=0,
        message="Searching Google Places...",
        log_type="work",
        log="● Searching Google Places...",
    )

    # If the user leaves --output at its default, create a descriptive
    # filename for this batch automatically.
    output_dir = Path(output_dir)
    codex_dir = Path(codex_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    codex_dir.mkdir(parents=True, exist_ok=True)
    if output == "leads.csv":
        output = str(output_dir / f"{safe_filename(niche)} - {safe_filename(area)}.csv")
    elif not Path(output).is_absolute():
        output = str(output_dir / output)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise SystemExit("ERROR: GOOGLE_MAPS_API_KEY is not set.")

    print(f"[info] Searching Google Places: {niche} in {area}")
    leads = google_places_search(niche, area, api_key, max_results)
    if not leads:
        print("[warn] No businesses found.")
        return

    print(f"[progress] Found {len(leads)} businesses. Starting website checks...", flush=True)
    progress(
        phase="Website analysis",
        subphase=f"{niche} • {area}",
        current_business="",
        current_index=0,
        total=len(leads),
        percent=5,
        high=0,
        medium=0,
        low=0,
        message=f"Found {len(leads)} businesses. Starting website checks...",
        log_type="ok",
        log=f"✓ Found {len(leads)} businesses.",
    )
    for number, lead in enumerate(leads, 1):
        print("", flush=True)
        print(f"[progress] ===== Lead {number}/{len(leads)} =====", flush=True)
        print(f"[lead] {lead.name}", flush=True)
        try:
            enrich_lead(lead)
        except Exception as exc:
            lead.website_status = "check failed"
            lead.opportunity_score = 0
            lead.opportunity = "LOW"
            lead.reason = f"website check failed: {exc}"
            print(f"       [warning] Website check failed: {exc}", flush=True)
        print(f"       [result] website={lead.website_status}, score={lead.opportunity_score}/100 ({lead.opportunity})", flush=True)
        high_count = sum(x.opportunity == "HIGH" for x in leads[:number])
        medium_count = sum(x.opportunity == "MEDIUM" for x in leads[:number])
        low_count = sum(x.opportunity == "LOW" for x in leads[:number])
        progress(
            phase="Website analysis",
            subphase=f"{niche} • {area}",
            current_business=lead.name,
            current_index=number,
            total=len(leads),
            percent=5 + int(number / len(leads) * 70),
            high=high_count,
            medium=medium_count,
            low=low_count,
            message=f"{lead.website_status.title()} • {lead.opportunity_score}/100 • {lead.opportunity}",
            log_type="ok",
            log=f"✓ {lead.name} — {lead.opportunity} — {lead.opportunity_score}/100",
        )
        time.sleep(random.uniform(0.2, 0.5))

    # Deterministic priority buckets.
    high_leads = [lead for lead in leads if lead.opportunity == "HIGH"]
    medium_leads = [lead for lead in leads if lead.opportunity == "MEDIUM"]
    low_leads = [lead for lead in leads if lead.opportunity == "LOW"]

    high_leads.sort(key=lambda x: (-x.opportunity_score, x.maps_position))
    medium_leads.sort(key=lambda x: (-x.opportunity_score, x.maps_position))
    low_leads.sort(key=lambda x: (-x.opportunity_score, x.maps_position))
    leads = high_leads + medium_leads + low_leads

    print(
        f"[progress] SORTED: HIGH={len(high_leads)} | "
        f"MEDIUM={len(medium_leads)} | LOW={len(low_leads)}",
        flush=True,
    )

    # Keep every priority in its own folder. LOW gets a lightweight business.json;
    # HIGH/MEDIUM get the full website-generator handoff.
    for priority, bucket in (("HIGH", high_leads), ("MEDIUM", medium_leads), ("LOW", low_leads)):
        priority_dir = Path(codex_dir) / priority
        priority_dir.mkdir(parents=True, exist_ok=True)
        print(f"[progress] Preparing {len(bucket)} {priority} priority records...", flush=True)
        progress(
            phase="Preparing handoffs",
            subphase=f"{priority} priority",
            current_business="",
            current_index=0,
            total=len(bucket),
            percent=75 if priority == "HIGH" else 85 if priority == "MEDIUM" else 92,
            high=len(high_leads),
            medium=len(medium_leads),
            low=len(low_leads),
            message=f"Preparing {len(bucket)} {priority} priority records...",
            log_type="work",
            log=f"● Preparing {len(bucket)} {priority} handoffs...",
        )
        for lead in bucket:
            print(f"       [handoff] {priority}: {lead.name}", flush=True)
            write_codex_handoff(lead, codex_dir)

    for priority, bucket in (("HIGH", high_leads), ("MEDIUM", medium_leads), ("LOW", low_leads)):
        write_opportunity_csv(
            bucket,
            output_dir / f"{safe_filename(niche)} - {safe_filename(area)} - {priority}.csv",
            priority,
        )

    # Also save a simple all-leads CSV in priority order.
    with open(output, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "business_name", "maps_position", "address", "phone", "website", "website_status",
            "facebook", "instagram", "linkedin", "other_socials", "email", "email_found_on",
            "opportunity_score", "opportunity", "opportunity_reasons",
        ])
        for lead in leads:
            writer.writerow([
                lead.name, lead.maps_position, lead.address, lead.phone, lead.website,
                lead.website_status, lead.facebook, lead.instagram, lead.linkedin, lead.other_socials,
                lead.email, lead.email_source_url, lead.opportunity_score, lead.opportunity,
                lead.reason,
            ])
    progress(
        phase="Complete",
        subphase=f"{niche} • {area}",
        current_business="",
        current_index=len(leads),
        total=len(leads),
        percent=100,
        high=len(high_leads),
        medium=len(medium_leads),
        low=len(low_leads),
        message=f"Lead generation complete. {len(leads)} leads ready.",
        log_type="ok",
        log=f"✓ Saved {len(leads)} leads.",
    )
    print(f"[done] Wrote {len(leads)} leads to {output}")
    print(f"[batch] {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--niche", required=True, help='e.g. "plumber"')
    parser.add_argument("--area", required=True, help='e.g. "Philadelphia, PA"')
    parser.add_argument("--output", default="leads.csv")
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()
    run(args.niche, args.area, args.output, args.max_results)


if __name__ == "__main__":
    main()
