import argparse
import json
import os
import re
import shutil
import ssl
from collections import Counter
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from openai import OpenAI

from api_usage_logger import log_usage


load_dotenv()

MODEL = "deepseek-chat"
ADMIRE_URL = "https://admiretheweb.com/"
TREE_PHOTOS = [
    {"url": "images/arborist_climbing.jpeg", "alt": "Illustrative stock photo: arborist climbing a tree", "credit": "John Robertson / Pexels", "source": "https://www.pexels.com/photo/professional-arborist-climbing-tree-for-maintenance-34674271/"},
    {"url": "images/pole_saw.jpeg", "alt": "Illustrative stock photo: arborist trimming a tree", "credit": "Samuel Vogl / Pexels", "source": "https://www.pexels.com/photo/man-in-helmet-cut-tree-with-equipment-5644617/"},
    {"url": "images/team_pruning.jpeg", "alt": "Illustrative stock photo: workers pruning trees", "credit": "Anna Shvets / Pexels", "source": "https://www.pexels.com/photo/colleagues-cutting-branches-with-garden-equipment-in-orchard-5231049/"},
    {"url": "images/pruning.jpeg", "alt": "Illustrative stock photo: worker pruning branches", "credit": "Mark Stebnicki / Pexels", "source": "https://www.pexels.com/photo/man-trimming-branches-7509490/"},
]


class GalleryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.item = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article" and "c-item" in attrs.get("class", "").split():
            self.item = {"name": [], "url": ""}
        elif self.item is not None and tag == "a":
            href = attrs.get("href", "")
            if href.startswith("/inspiration/") and not self.item["url"]:
                self.item["url"] = href

    def handle_data(self, data):
        if self.item is not None and data.strip():
            self.item["name"].append(data.strip())

    def handle_endtag(self, tag):
        if tag == "article" and self.item is not None:
            self.item["name"] = " ".join(self.item["name"]).replace("Save ", "", 1)
            if self.item["url"]:
                self.items.append(self.item)
            self.item = None


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.in_title = False
        self.headings = []
        self.heading = None
        self.images = []
        self.stylesheets = []
        self.styles = []
        self.buttons = []
        self.sections = 0
        self.tags = Counter()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags[tag] += 1
        if tag == "title":
            self.in_title = True
        elif tag in ("h1", "h2", "h3"):
            self.heading = [tag, []]
        elif tag == "section":
            self.sections += 1
        elif tag == "img" and attrs.get("alt"):
            self.images.append(attrs["alt"][:100])
        elif tag == "link" and "stylesheet" in attrs.get("rel", "").lower():
            if attrs.get("href"):
                self.stylesheets.append(attrs["href"])
        elif tag == "style":
            self.styles.append("")
        elif tag == "button" or (tag == "a" and re.search(r"button|btn|cta", attrs.get("class", ""), re.I)):
            self.buttons.append(attrs.get("aria-label") or attrs.get("title") or attrs.get("class", "button")[:60])
        if attrs.get("style"):
            self.styles.append(attrs["style"][:500])

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data.strip())
        if self.heading is not None and data.strip():
            self.heading[1].append(data.strip())
        if self.styles and self.get_starttag_text() and "<style" in self.get_starttag_text().lower():
            self.styles[-1] += data[:3000]

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif self.heading is not None and tag == self.heading[0]:
            self.headings.append(" ".join(self.heading[1])[:120])
            self.heading = None


class BusinessPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.description = ""
        self.in_title = False
        self.skip = 0
        self.text = []
        self.headings = []
        self.heading = None
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("name", "").lower() == "description":
            self.description = attrs.get("content", "")[:400]
        if tag in ("h1", "h2", "h3"):
            self.heading = [tag, []]
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "img" and attrs.get("src"):
            self.images.append({"src": attrs["src"], "alt": attrs.get("alt", "")[:120]})

    def handle_data(self, data):
        if self.skip:
            return
        clean = " ".join(data.split())
        if self.in_title and clean:
            self.title.append(clean)
        if clean:
            self.text.append(clean)
            if self.heading is not None:
                self.heading[1].append(clean)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if self.heading is not None and tag == self.heading[0]:
            heading = " ".join(self.heading[1]).strip()
            if heading:
                self.headings.append(heading[:150])
            self.heading = None


def find_tree_services(business_name, text):
    if "tree" not in business_name:
        return {}
    patterns = (
        ("Emergency Tree & Crane Services", r"\bemergency\b.{0,80}\b(?:tree|crane)"),
        ("Tree Removal Services", r"\btree removal\b"),
        ("Tree Trimming", r"\btrim(?:ming)?\b"),
        ("Tree Pruning", r"\bprun(?:e|ing)\b"),
        ("Stump Grinding & Removal Services", r"\bstump grind(?:ing)?\b"),
        ("Local Wood Chip Deliveries", r"\bwood chips?\b.{0,60}\bdeliver"),
    )
    sentences = re.split(r"(?<=[.!?])\s+", text)
    found = {}
    for label, pattern in patterns:
        matches = [sentence for sentence in sentences if re.search(pattern, sentence, re.I)]
        if matches:
            found[label] = " ".join(dict.fromkeys(matches))[:280]
    return found


def research_business(business):
    """Read the supplied business site and a few relevant pages; never search by name."""
    website = str(business.get("website") or "").strip()
    parsed = urlparse(website)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return {"business_website": website, "pages": [], "services": [], "images": [], "note": "No usable business website URL was supplied."}

    host = parsed.hostname.removeprefix("www.")
    base_path = parsed.path or "/"
    queue = list(dict.fromkeys((
        website,
        f"https://{host}{base_path}",
        f"https://www.{host}{base_path}",
        f"http://{host}{base_path}",
    )))
    pages, services, images, errors, seen = [], [], [], [], set()
    business_name = re.sub(r"[^a-z0-9]+", "", str(business.get("business_name", "")).lower())
    service_pattern = re.compile(r"\b(?:tree|stump|crane|wood chip|emergency).*(?:service|delivery|removal|trimming|pruning|grinding|crane)\b", re.I)
    non_service_pattern = re.compile(r"\b(testimonials?|reviews?|about|contact|gallery)\b", re.I)
    service_details = {}

    while queue and len(pages) < 3:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html, final_url = fetch_page(url, limit=800_000, timeout=12)
        except HTTPError as error:
            errors.append({"type": "HTTPError", "status": error.code})
            continue
        except (URLError, RuntimeError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            errors.append({"type": type(error).__name__, "reason_type": type(reason).__name__})
            continue
        page = BusinessPageParser()
        page.feed(html)
        pages.append({
            "url": final_url,
            "title": " ".join(page.title)[:160],
            "description": page.description,
            "headings": page.headings[:24],
            "text": " ".join(page.text)[:2600],
        })
        if "tree" not in business_name:
            services.extend(heading for heading in page.headings
                            if service_pattern.search(heading) and not non_service_pattern.search(heading)
                            and (not business_name or business_name not in re.sub(r"[^a-z0-9]+", "", heading.lower())))
        details = find_tree_services(business_name, pages[-1]["text"])
        services.extend(details)
        service_details.update(details)
        for image in page.images:
            image_url = urljoin(final_url, image["src"])
            image_host = (urlparse(image_url).hostname or "").removeprefix("www.")
            if image_host == host and not re.search(r"logo|icon|badge|star|facebook|google", image["src"] + image["alt"], re.I) and image_url not in {item["url"] for item in images}:
                images.append({"url": image_url, "alt": image["alt"]})
        candidates = []
        for link in page.links:
            candidate = urljoin(final_url, link).split("#", 1)[0]
            parts = urlparse(candidate)
            if parts.scheme not in ("http", "https") or (parts.hostname or "").removeprefix("www.") != host or candidate in seen:
                continue
            path = parts.path.lower()
            score = sum(word in path for word in ("service", "tree", "about", "emergency", "contact", "stump", "crane"))
            if score:
                candidates.append((score, candidate))
        queue.extend(url for _, url in sorted(set(candidates), reverse=True))

    if not pages:
        search_terms = "tree removal trimming pruning emergency crane stump grinding" if "tree" in business_name else "services"
        results, search_error = tavily_search(f'site:{host} "{business.get("business_name", "")}" {search_terms}', host)
        for result in results:
            result_host = (urlparse(result["url"]).hostname or "").removeprefix("www.")
            if result_host != host:
                continue
            text = " ".join([result.get("description", ""), *result.get("snippets", [])]).strip()
            pages.append({"url": result["url"], "title": result["title"], "description": result.get("description", ""), "headings": [result["title"]], "text": text[:1800], "source_type": "first-party search result"})
            if "tree" not in business_name and service_pattern.search(result["title"]) and not non_service_pattern.search(result["title"]):
                services.append(result["title"])
            details = find_tree_services(business_name, text)
            services.extend(details)
            service_details.update(details)
        errors.append({"type": "TavilySearch", "reason": search_error} if search_error else {"type": "TavilySearch", "results": len(pages)})

    return {
        "business_website": website,
        "pages": pages,
        "services": list(dict.fromkeys(services))[:12],
        "service_details": service_details,
        "images": images[:12],
        "fetch_errors": errors[:8],
        "note": "Research is limited to pages and search snippets from the supplied website's domain.",
    }


def tavily_search(query, domain):
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return [], "TAVILY_API_KEY is not set"
    request = Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": query, "search_depth": "basic", "max_results": 5,
                         "include_domains": [domain], "include_raw_content": False,
                         "include_answer": False}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=12, context=ssl_context()) as response:
            payload = json.loads(response.read(1_000_000))
    except HTTPError as error:
        return [], f"search returned HTTP {error.code}"
    except json.JSONDecodeError:
        return [], "search returned invalid JSON"
    except URLError as error:
        reason = error.reason
        if isinstance(reason, ssl.SSLError):
            return [], "TLS certificate validation failed"
        return [], f"connection failed ({type(reason).__name__})"
    except TimeoutError:
        return [], "search timed out"
    except OSError as error:
        return [], f"network error ({type(error).__name__})"
    results = payload.get("results", [])
    return [
        {"url": item.get("url", ""), "title": item.get("title", "")[:180],
         "description": item.get("content", "")[:1800], "snippets": []}
        for item in results if item.get("url", "").startswith(("https://", "http://"))
    ], None


def load_or_research_business(handoff_path, business):
    path = Path(handoff_path).parent / "business_research.json"
    try:
        saved = load_json(path)
        if saved.get("business_website") == business.get("website") and saved.get("pages"):
            names = re.sub(r"[^a-z0-9]+", "", str(business.get("business_name", "")).lower())
            for page in saved["pages"]:
                details = find_tree_services(names, page.get("text", ""))
                saved.setdefault("service_details", {}).update(details)
                saved.setdefault("services", []).extend(details)
            saved["services"] = list(dict.fromkeys(saved.get("services", [])))
            path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return saved
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    research = research_business(business)
    path.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return research


def ssl_context():
    ca_bundle = os.environ.get("SSL_CERT_FILE")
    if not ca_bundle and Path("/etc/ssl/cert.pem").is_file():
        ca_bundle = "/etc/ssl/cert.pem"
    return ssl.create_default_context(cafile=ca_bundle)


def fetch_page(url, limit=1_500_000, timeout=25):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"})
    with urlopen(request, timeout=timeout, context=ssl_context()) as response:
        content_type = response.headers.get_content_type()
        if content_type not in ("text/html", "application/xhtml+xml", "text/css"):
            raise RuntimeError(f"Expected HTML or CSS at {url}.")
        body = response.read(limit + 1)
        if len(body) > limit:
            raise RuntimeError(f"Page exceeded the {limit}-byte analysis limit.")
        return body.decode(response.headers.get_content_charset() or "utf-8", "replace"), response.geturl()


def discover_reference():
    gallery_html, _ = fetch_page(ADMIRE_URL)
    gallery = GalleryParser()
    gallery.feed(gallery_html)
    ignored_hosts = {"admiretheweb.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "google.com", "feedburner.com", "linkedin.com", "pinterest.com", "youtube.com", "tiktok.com"}
    for item in gallery.items:
        detail_html, detail_url = fetch_page(urljoin(ADMIRE_URL, item["url"]))
        links = LinkParser()
        links.feed(detail_html)
        for href in links.urls:
            candidate = urljoin(detail_url, href)
            parsed = urlparse(candidate)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            if parsed.scheme in ("http", "https") and host and not any(host == blocked or host.endswith("." + blocked) for blocked in ignored_hosts) and not parsed.path.startswith("/intent/"):
                return {"name": item["name"] or host, "url": candidate}
    raise RuntimeError("Admire The Web returned no submitted-site URLs in its .c-item entries.")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("http://", "https://")):
                self.urls.append(href)


def analyze_reference(reference):
    page, final_url = fetch_page(reference["url"])
    parser = PageParser()
    parser.feed(page)
    css = " ".join(parser.styles)
    for stylesheet in parser.stylesheets[:3]:
        try:
            stylesheet_text, _ = fetch_page(urljoin(final_url, stylesheet), limit=500_000)
            css += " " + stylesheet_text
        except (HTTPError, URLError, RuntimeError):
            continue
    colors = list(dict.fromkeys(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]{1,40}\)|\b(?:black|white|navy|beige|coral|teal)\b", css)))[:8]
    fonts = list(dict.fromkeys(re.findall(r"(?:font-family\s*:\s*|family=)([^;\"&}]{2,60})", css, re.I)))[:4]
    return {
        "page_title": " ".join(parser.title)[:120],
        "page_url": final_url,
        "layout_signals": {"sections": parser.sections, "columns_or_grids": bool(re.search(r"display\s*:\s*(?:grid|flex)", css, re.I))},
        "headings": parser.headings[:8],
        "typography_signals": fonts,
        "color_signals": colors,
        "component_signals": {"buttons": parser.buttons[:5], "cards": parser.tags["article"] + parser.tags["li"]},
        "image_alt_examples": parser.images[:5],
    }


DESIGN_DIRECTOR_PROMPT = """Create an original, implementable design_spec for Brown's Tree Service from the supplied facts and reference_analysis. Transfer visual principles only; copy no brand, text, or assets; invent no business claims. Return only JSON with exactly these keys: layout, header, hero, typography, palette, spacing, components, imagery, section_composition, visual_hierarchy. Keep each text value to 8 words maximum; palette is an array of up to 5 CSS colors."""


def create_design_spec(business, reference, analysis):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": DESIGN_DIRECTOR_PROMPT},
            {"role": "user", "content": json.dumps({"business": {"name": business.get("business_name"), "address": business.get("address"), "phone": business.get("phone")}, "reference": reference, "reference_analysis": analysis}, ensure_ascii=False, separators=(",", ":"))},
        ],
        temperature=0.2,
        max_tokens=450,
    )
    try:
        spec = json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"DeepSeek returned invalid design_spec JSON: {error}") from error
    required = {"layout", "header", "hero", "typography", "palette", "spacing", "components", "imagery", "section_composition", "visual_hierarchy"}
    text_fields = required - {"palette"}
    if (
        not required.issubset(spec)
        or any(not isinstance(spec[key], str) or not spec[key].strip() for key in text_fields)
        or not isinstance(spec["palette"], list)
        or not spec["palette"]
        or any(not isinstance(color, str) or not color.strip() for color in spec["palette"])
    ):
        raise RuntimeError("DeepSeek design_spec failed validation.")
    return spec, response.usage


def generate_reference_analysis(handoff_path):
    handoff_path = Path(handoff_path)
    business = load_json(handoff_path.parent / "business.json")
    reference = discover_reference()
    analysis = analyze_reference(reference)
    spec, usage = create_design_spec(business, reference, analysis)
    artifact = {"business": business.get("business_name") or "Brown's Tree Service", "reference": reference, "reference_analysis": analysis, "design_spec": spec}
    output = handoff_path.parent / "reference_analysis.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        log_usage(artifact["business"], usage)
    except Exception as error:
        print(f"Usage logging skipped: {error}")
    return output


SYSTEM_PROMPT = """Write website copy from the supplied business facts and first-party website research. Research text is the source of truth; do not invent claims, ratings, years, credentials, prices, guarantees, or services. List only services present in the research services list, using each supplied name exactly; describe only details supported by the research text. Make the copy specific to this business, not generic advice or a visitor guide. Return JSON with exactly: headline, subheadline, intro_title, intro, services (up to 6 objects with exact supplied name and concise grounded description), proof_points (up to 3 objects with title and text grounded in research), cta_title, cta_text. Keep text concise and natural."""


CSS = r"""
:root { --bg: __BG__; --text: __TEXT__; --muted: color-mix(in srgb,__TEXT__ 66%,__BG__); --gold: __ACCENT__; --gold-light: __WARM__; --surface: __SURFACE__; --line: color-mix(in srgb,__TEXT__ 14%,transparent); --max: 1240px; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,sans-serif; }
body:before { content:""; position:fixed; z-index:10; inset:0 auto auto 0; width:var(--page-progress,0%); height:3px; background:linear-gradient(90deg,#d8b663,#a8c28e); pointer-events:none; }
a { color:inherit; text-decoration:none; }
.site-header { position:sticky; z-index:5; top:0; width:100%; max-width:none; height:90px; margin:0 0 -90px; padding:0 max(5vw,calc((100vw - var(--max))/2 + 62px)); display:flex; justify-content:space-between; align-items:center; color:#fff; border-bottom:1px solid #ffffff35; background:rgba(15,31,22,.78); backdrop-filter:blur(14px); }
section[id] { scroll-margin-top:110px; }
.brand { display:flex; align-items:center; gap:12px; font-size:1.05rem; font-weight:750; letter-spacing:-.03em; }
.brand-mark { width:36px; height:36px; display:grid; place-items:center; border:1px solid #d8b663; border-radius:50%; color:#e6ce93; font:600 1rem Georgia,serif; }
.site-header nav { display:flex; align-items:center; gap:30px; font-size:.9rem; }
.site-header nav a { color:#ffffffd9; }
.site-header nav a:not(.nav-call) { padding:8px 0; border-bottom:1px solid transparent; transition:border-color .2s,color .2s; }
.site-header nav a:not(.nav-call):hover { color:#fff; border-color:#d8b663; }
.site-header nav .nav-call { padding:11px 18px; border:1px solid #d8b663; border-radius:2px; color:white; }
.hero { position:relative; isolation:isolate; min-height:min(800px,90svh); padding:160px max(7vw,calc((100vw - var(--max))/2)) 115px; display:flex; align-items:center; overflow:hidden; background:#15271d; color:white; }
.hero-image { position:absolute; z-index:-2; inset:0; width:100%; height:100%; object-fit:cover; object-position:center 42%; }
.hero-image { animation:hero-image-in .9s ease-out both; transform:translate3d(0,var(--hero-shift,0px),0) scale(1.025); }
.hero:after { content:""; position:absolute; z-index:-1; inset:0; background:linear-gradient(90deg,rgba(8,23,15,.92),rgba(8,23,15,.68) 46%,rgba(8,23,15,.1)),linear-gradient(0deg,rgba(8,23,15,.45),transparent 48%); }
.hero-copy { position:relative; z-index:1; max-width:760px; padding-left:28px; border-left:2px solid #d8b663; }
.hero-copy { animation:hero-copy-in .65s .08s ease-out both; }
@keyframes hero-copy-in { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
@keyframes hero-image-in { from { opacity:.65; } to { opacity:1; } }
.eyebrow { margin:0 0 22px; color:var(--gold); font:650 .72rem/1.3 system-ui,sans-serif; letter-spacing:.16em; text-transform:uppercase; }
.hero .eyebrow { color:#e6ce93; }
.hero h1 { max-width:760px; margin:0; color:#fff; font-family:Georgia,'Times New Roman',serif; font-size:clamp(4rem,8.5vw,7.8rem); line-height:.9; letter-spacing:-.06em; font-weight:500; text-wrap:balance; }
.lead { max-width:500px; margin:24px 0 0; color:rgba(255,255,255,.9); font-size:clamp(1.1rem,2vw,1.3rem); }
.hero-credit { position:absolute; right:18px; bottom:18px; z-index:2; padding:7px 11px; border:1px solid #ffffff55; border-radius:2px; background:#0f1712b8; color:white; font-size:.68rem; }
.hero-credit a { text-decoration:underline; }
.button { display:inline-flex; align-items:center; justify-content:center; min-height:54px; margin-top:28px; padding:0 24px; border-radius:2px; background:#d8b663; color:#17291e; font-weight:750; transition:transform .2s,background .2s; }
.button:hover { transform:translateY(-2px); background:#ead49b; }
.facts { display:flex; flex-wrap:wrap; justify-content:center; gap:12px 44px; margin:auto; padding:22px 5%; background:#1d3828; color:#f8f5eb; text-align:center; }
.facts div { font-size:.76rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }
.facts .step { color:#d9e4b0; font-size:.68rem; }
.facts a { text-decoration:underline; text-underline-offset:3px; }
.about { max-width:var(--max); margin:auto; padding:120px 5%; display:grid; grid-template-columns:1.1fr .9fr; gap:8%; align-items:center; }
.about-photo { position:relative; height:460px; overflow:hidden; border-radius:3px; background:var(--surface); }
.about-image { width:100%; height:100%; object-fit:cover; }
.about-copy .eyebrow { margin-bottom:18px; }
.about-copy h2 { margin:0 0 18px; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.3rem,4vw,4rem); line-height:1.04; letter-spacing:-.045em; font-weight:500; }
.about-copy > p:last-child { max-width:560px; margin:0; color:var(--muted); font-size:1.08rem; }
.need-section { max-width:var(--max); margin:0 auto; padding:8px 5% 94px; }
.need-section h2 { margin:0 0 30px; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.5rem,5vw,4.5rem); line-height:1; letter-spacing:-.05em; font-weight:500; }
.need-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:0 28px; }
.need-grid article { min-height:225px; padding:22px 22px 24px 0; border-top:1px solid var(--line); }
.need-grid h3 { margin:18px 0 10px; font-family:Georgia,'Times New Roman',serif; font-size:1.8rem; line-height:1.1; font-weight:500; }
.need-grid p { color:var(--muted); }
.need-grid a { display:inline-block; margin-top:8px; color:var(--gold); font-weight:700; text-decoration:underline; text-underline-offset:4px; }
.services { max-width:none; margin:0 auto; padding:94px max(7vw,calc((100vw - var(--max))/2)) 112px; background:#1d3828; color:#f8f5eb; }
.service-heading { margin-bottom:38px; }
.service-heading .eyebrow { margin:0 0 12px; }
.services .eyebrow { color:#d8b663; }
.service-heading h2 { max-width:760px; margin:0; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.7rem,5vw,4.8rem); line-height:.98; letter-spacing:-.05em; font-weight:500; }
.service-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }
.service-grid article { min-height:210px; padding:24px 24px 24px 0; border-top:1px solid #ffffff45; background:transparent; }
.service-grid .eyebrow { color:#d8b663; }
.service-grid h3 { margin:16px 0 10px; font-family:Georgia,'Times New Roman',serif; font-size:1.7rem; line-height:1.1; font-weight:500; }
.service-grid p { max-width:500px; margin:0; color:#ffffffc9; }
.field-notes { max-width:var(--max); margin:0 auto; padding:0 5% 92px; }
.field-notes h2,.reviews h2 { margin:0 0 30px; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.3rem,4vw,3.8rem); line-height:1; letter-spacing:-.045em; font-weight:500; }
.photo-grid { display:grid; grid-template-columns:1.15fr 1fr 1fr; grid-template-rows:190px 190px; gap:10px; }
.photo-grid figure { position:relative; height:100%; margin:0; overflow:hidden; background:var(--surface); }
.photo-grid figure:first-child { grid-column:1; grid-row:1 / span 2; }
.photo-grid figure:nth-child(3) { grid-column:3; grid-row:1 / span 2; }
.photo-grid img { width:100%; height:100%; object-fit:cover; transition:transform .35s; }
.photo-grid figure:hover img { transform:scale(1.04); }
.photo-grid figcaption { position:absolute; inset:auto 0 0; padding:24px 14px 12px; color:white; font-size:.76rem; background:linear-gradient(transparent,#0c1711cc); }
html.scroll-effects-ready .about .about-photo { clip-path:inset(0 100% 0 0); transition:clip-path .95s cubic-bezier(.2,.75,.2,1); }
html.scroll-effects-ready .about.is-visible .about-photo { clip-path:inset(0); }
html.scroll-effects-ready .need-grid article { opacity:0; transform:translateX(-22px); transition:opacity .45s ease,transform .65s cubic-bezier(.2,.75,.2,1); }
.need-section.is-visible .need-grid article { opacity:1; transform:none; }
.need-section.is-visible .need-grid article:nth-child(2) { transition-delay:.12s; }
.need-section.is-visible .need-grid article:nth-child(3) { transition-delay:.24s; }
html.scroll-effects-ready .service-grid article { opacity:0; transform:translateY(24px); transition:opacity .5s ease,transform .7s cubic-bezier(.2,.75,.2,1); }
.services.is-visible .service-grid article { opacity:1; transform:none; }
.services.is-visible .service-grid article:nth-child(2),.services.is-visible .service-grid article:nth-child(5) { transition-delay:.1s; }
.services.is-visible .service-grid article:nth-child(3),.services.is-visible .service-grid article:nth-child(6) { transition-delay:.2s; }
html.scroll-effects-ready .photo-grid figure { clip-path:inset(100% 0 0 0); transition:clip-path .85s cubic-bezier(.2,.75,.2,1); }
html.scroll-effects-ready .photo-grid img { transform:scale(1.1); transition:transform 1.1s cubic-bezier(.2,.75,.2,1); }
.field-notes.is-visible .photo-grid figure { clip-path:inset(0); }
.field-notes.is-visible .photo-grid img { transform:scale(1); }
.field-notes.is-visible .photo-grid figure:nth-child(2) { transition-delay:.12s; }
.field-notes.is-visible .photo-grid figure:nth-child(2) img { transition-delay:.12s; }
html.scroll-effects-ready .owner-note { clip-path:inset(0 100% 0 0); transition:clip-path .8s cubic-bezier(.2,.75,.2,1); }
html.scroll-effects-ready .owner-note.is-visible { clip-path:inset(0); }
html.scroll-effects-ready .review-grid blockquote { opacity:0; transform:translateX(20px); transition:opacity .5s ease,transform .7s cubic-bezier(.2,.75,.2,1); }
.reviews.is-visible .review-grid blockquote { opacity:1; transform:none; }
.reviews.is-visible .review-grid blockquote:nth-child(2) { transition-delay:.16s; }
html.scroll-effects-ready .tree-notes > * { opacity:0; transform:translateY(18px); transition:opacity .55s ease,transform .7s cubic-bezier(.2,.75,.2,1); }
html.scroll-effects-ready .tree-notes.is-visible > * { opacity:1; transform:none; }
html.scroll-effects-ready .tree-notes.is-visible > :nth-child(2) { transition-delay:.15s; }
html.scroll-effects-ready .contact { opacity:0; transform:scale(.975); transition:opacity .55s ease,transform .7s cubic-bezier(.2,.75,.2,1); }
html.scroll-effects-ready .contact.is-visible { opacity:1; transform:scale(1); }
.owner-note { max-width:var(--max); margin:0 auto 90px; padding:58px 7%; display:grid; grid-template-columns:.7fr 1.3fr; gap:7%; align-items:center; background:#e9e7d9; border-left:4px solid #d8b663; }
.owner-note h2 { margin:0; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.2rem,4vw,3.8rem); line-height:1.02; font-weight:500; }
.owner-note p:last-child { margin:0; color:var(--muted); font-size:1.08rem; }
.reviews { max-width:var(--max); margin:0 auto; padding:0 5% 100px; }
.review-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }
.review-grid blockquote { margin:0; padding:26px 28px; border-left:2px solid #d8b663; background:transparent; font-family:Georgia,'Times New Roman',serif; font-size:1.45rem; line-height:1.45; }
.review-grid cite { display:block; margin-top:20px; color:var(--muted); font:600 .74rem system-ui,sans-serif; letter-spacing:.08em; text-transform:uppercase; }
.reviews > a { display:inline-block; margin-top:18px; text-decoration:underline; text-underline-offset:4px; }
.tree-notes { max-width:var(--max); margin:0 auto; padding:24px 5% 112px; display:grid; grid-template-columns:1fr 1fr; gap:9%; align-items:start; }
.tree-notes h2 { max-width:520px; margin:0 0 18px; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.3rem,4vw,3.7rem); line-height:1.04; letter-spacing:-.045em; font-weight:500; }
.tree-notes p { color:var(--muted); }
.tree-notes .button { margin-top:12px; }
.tree-notes .source { display:block; margin-top:14px; color:var(--muted); font-size:.78rem; }
.tree-notes .source a { text-decoration:underline; text-underline-offset:3px; }
.tree-faq { border-top:1px solid var(--line); }
.tree-faq .eyebrow { margin:0; padding:18px 0; }
.tree-faq details { border-top:1px solid var(--line); }
.tree-faq summary { padding:18px 24px 18px 0; cursor:pointer; font-weight:700; }
.tree-faq details p { margin:0; padding:0 0 20px; }
.contact { max-width:calc(var(--max) - 10%); margin:0 auto 78px; padding:58px 7%; display:flex; flex-wrap:wrap; align-items:center; gap:12px 36px; background:#1f3829; color:white; border-radius:3px; }
.contact .eyebrow { width:100%; color:#d9e4b0; margin:0; }
.contact h2 { flex:1 1 420px; margin:0; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.2rem,5vw,4.1rem); line-height:1; letter-spacing:-.045em; font-weight:500; }
.contact > p:not(.eyebrow) { flex:1 1 250px; color:#ffffffc9; }
.contact .button { background:#d8b663; color:#17291e; }
.contact > a:not(.button) { flex-basis:100%; margin:0; color:#ffffffd9; text-decoration:underline; text-underline-offset:4px; }
footer { max-width:var(--max); margin:auto; padding:24px 5%; display:flex; justify-content:space-between; gap:20px; border-top:1px solid var(--line); color:var(--muted); font-size:.85rem; }
@media(max-width:980px) { .service-grid { grid-template-columns:repeat(2,1fr); } .photo-grid { grid-template-columns:repeat(2,1fr); grid-template-rows:190px 190px; } .photo-grid figure:first-child,.photo-grid figure:nth-child(3) { grid-column:auto; grid-row:auto; } }
@media(max-width:720px) { .site-header { height:76px; margin-bottom:-76px; padding:0 6%; } section[id] { scroll-margin-top:90px; } .site-header nav { gap:14px; font-size:.8rem; } .site-header nav a:not(.nav-call) { display:none; } .hero { min-height:700px; padding:120px 7% 75px; } .hero-copy { padding-left:18px; } .hero h1 { font-size:clamp(3.6rem,15vw,6rem); } .facts { gap:12px 20px; padding:18px 6%; } .facts div { font-size:.68rem; } .about { padding:72px 6%; grid-template-columns:1fr; gap:30px; } .about-photo { height:300px; } .need-section { padding:0 6% 72px; } .need-grid { grid-template-columns:1fr; gap:10px; } .need-grid article { min-height:0; padding:20px 0; } .services { padding:58px 6% 72px; } .service-grid,.review-grid { grid-template-columns:1fr; gap:12px; } .service-grid article { min-height:0; padding:22px 0; } .tree-notes { padding:10px 6% 72px; grid-template-columns:1fr; gap:35px; } .field-notes,.reviews { padding:0 6% 72px; } .photo-grid { grid-template-columns:1fr 1fr; grid-template-rows:none; gap:8px; } .photo-grid figure,.photo-grid figure:first-child,.photo-grid figure:nth-child(3) { grid-column:auto; grid-row:auto; height:190px; } .owner-note { margin:0 6% 72px; padding:34px 26px; grid-template-columns:1fr; gap:15px; } .contact { margin:0 6% 48px; padding:38px 28px; } footer { padding:22px 6%; flex-direction:column; gap:5px; } }
@media(prefers-reduced-motion:reduce) { html { scroll-behavior:auto; } *,*::before,*::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; } }
"""

def css_for_design_spec(design_spec):
    defaults = {"BG": "#F5F0E6", "TEXT": "#1A1A1A", "SURFACE": "#FFFFFF", "ACCENT": "#3E5C3A", "WARM": "#8B6F47"}
    palette = [c.upper() for c in design_spec.get("palette", []) if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", c)][:5]

    def channels(color):
        value = color[1:]
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    if len(palette) >= 3:
        lightness = lambda color: sum(channels(color))
        ranked = sorted(palette, key=lightness)
        light = [color for color in ranked if lightness(color) > 550]
        defaults["TEXT"] = ranked[0]
        defaults["BG"] = light[-2] if len(light) > 1 else (light[-1] if light else defaults["BG"])
        defaults["SURFACE"] = next((color for color in light if color != defaults["BG"]), defaults["BG"])
        remaining = [color for color in ranked if color not in (defaults["TEXT"], defaults["BG"], defaults["SURFACE"])]
        green = next((color for color in remaining if channels(color)[1] > channels(color)[0] * .9 and channels(color)[1] > channels(color)[2] * 1.15), None)
        defaults["ACCENT"] = green or (remaining[0] if remaining else defaults["ACCENT"])
        defaults["WARM"] = next((color for color in remaining if color != defaults["ACCENT"]), defaults["ACCENT"])
    elif palette:
        defaults["BG"] = palette[0]
        defaults["TEXT"] = palette[1] if len(palette) > 1 else defaults["TEXT"]
        defaults["ACCENT"] = palette[2] if len(palette) > 2 else defaults["ACCENT"]

    css = CSS
    for key, value in defaults.items():
        css = css.replace(f"__{key}__", value)
    return css

JS = r"""
var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function () {
        var target = document.querySelector(
            link.getAttribute("href")
        );

        if (target) {
            target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
        }
    });
});

if (!reduceMotion && "IntersectionObserver" in window) {
    var revealItems = document.querySelectorAll(".scroll-reveal");
    var revealObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("is-visible");
                revealObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12 });
    document.documentElement.classList.add("scroll-effects-ready");
    revealItems.forEach(function (item) { revealObserver.observe(item); });

    var heroImage = document.querySelector(".hero-image");
    var hero = document.querySelector(".hero");
    if (heroImage && hero) {
        var queued = false;
        window.addEventListener("scroll", function () {
            if (queued) return;
            queued = true;
            window.requestAnimationFrame(function () {
                var scrollable = document.documentElement.scrollHeight - window.innerHeight;
                document.documentElement.style.setProperty("--page-progress", (scrollable > 0 ? window.scrollY / scrollable * 100 : 0) + "%");
                heroImage.style.setProperty("--hero-shift", Math.min(window.scrollY, hero.offsetHeight) * 0.2 + "px");
                queued = false;
            });
        }, { passive: true });
        window.dispatchEvent(new Event("scroll"));
    }
}
"""


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def get_business_name(business, handoff):
    return (
        business.get("business_name")
        or business.get("name")
        or handoff.get("business_name")
        or handoff.get("business", {}).get("business_name")
        or handoff.get("business", {}).get("name")
        or "Local Business"
    )


def phone_link(phone):
    if not phone:
        return ""

    digits = "".join(
        c for c in str(phone)
        if c.isdigit() or c == "+"
    )

    return (
        f'<a class="button primary" href="tel:{escape(digits)}">'
        f"Call Now"
        f"</a>"
    )


def generate_business_content(business, handoff, research):
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    source = json.dumps(
        {
            "business": {key: business.get(key) for key in ("business_name", "address", "phone", "website")},
            "business_research": research,
            "website_requirements": handoff.get("website_build", {}).get("requirements", []),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": source,
            },
        ],
        temperature=0.5,
        max_tokens=900,
    )

    print("\nDeepSeek Usage:")
    print(response.usage)

    try:
        log_usage(
            get_business_name(business, handoff),
            response.usage,
        )
    except Exception as error:
        print(
            f"Usage logging skipped: {error}"
        )

    content = response.choices[0].message.content or "{}"

    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"DeepSeek returned invalid JSON: {error}"
        )


def verified_business_content(business, generated, research):
    """Keep listed services tied to exact headings from the first-party crawl."""
    if not isinstance(generated, dict):
        generated = {}
    name = get_business_name(business, {})
    address = business.get("address", "")
    parts = [part.strip() for part in address.split(",")]
    location = ", ".join(parts[-3:-1]) if len(parts) >= 3 else ""
    location = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", location)
    is_tree = "tree" in name.lower()
    fallback = {
        "headline": f"Tree work across {location}" if is_tree and location else name,
        "subheadline": f"{name} · {location}" if location else name,
        "intro_title": f"Tree care in {location}" if is_tree and location else name,
        "intro": f"Call {name} to ask about current availability and services.",
        "cta_title": f"Talk with {name}",
        "cta_text": f"Call {business.get('phone', '')} to discuss the work you need.",
    }
    content = {}
    for key, default in fallback.items():
        value = generated.get(key)
        if isinstance(default, str):
            value = str(value).strip() if value is not None else ""
            content[key] = value[:280] if value else default
    def normalize(value):
        return re.sub(r"[^a-z0-9]+", "", str(value).lower())
    allowed = {normalize(item) for item in research.get("services", [])}
    generated_services = generated.get("services", [])
    content["services"] = [
        {"name": next(title for title in research["services"] if normalize(title) == normalize(item["name"])), "description": str(item.get("description", ""))[:280]}
        for item in (generated_services[:4] if isinstance(generated_services, list) else [])
        if isinstance(item, dict) and normalize(item.get("name", "")) in allowed
    ]
    included = {normalize(item["name"]) for item in content["services"]}
    content["services"].extend(
        {"name": name, "description": str(research.get("service_details", {}).get(name, ""))[:280]}
        for name in research.get("services", [])
        if normalize(name) not in included and research.get("service_details", {}).get(name)
    )
    content["services"] = content["services"][:6]
    content["proof_points"] = [
        {"title": str(item.get("title", ""))[:80], "text": str(item.get("text", ""))[:240]}
        for item in (generated.get("proof_points", [])[:3] if isinstance(generated.get("proof_points", []), list) else [])
        if isinstance(item, dict) and item.get("title") and item.get("text")
    ]
    content["business_name"] = name
    content["research_sources"] = [page["url"] for page in research.get("pages", [])]
    content["content_gaps"] = [label for key, label in (
        ("services", "Could not verify service details on the business website"),
        ("pages", "Could not research the supplied business website"),
    ) if not research.get(key)]
    return content


def generate_content_only(handoff_path):
    handoff_path = Path(handoff_path)
    handoff = load_json(handoff_path)
    business_path = handoff_path.parent / "business.json"
    if not business_path.exists():
        raise RuntimeError("business.json not found.")
    business = load_json(business_path)
    research = load_or_research_business(handoff_path, business)
    research_path = handoff_path.parent / "business_research.json"
    if not research.get("pages"):
        raise RuntimeError(f"Could not read the supplied business website. See {research_path}; no DeepSeek request was made.")
    content = verified_business_content(business, generate_business_content(business, handoff, research), research)
    output = handoff_path.parent / "business_content.json"
    output.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def generate_research_only(handoff_path):
    handoff_path = Path(handoff_path)
    business_path = handoff_path.parent / "business.json"
    if not business_path.exists():
        raise RuntimeError("business.json not found.")
    research = research_business(load_json(business_path))
    output = handoff_path.parent / "business_research.json"
    output.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def build_html(business, content, design_spec=None, research=None):
    research = research or {}
    name = get_business_name(business, {})
    phone, address = business.get("phone", ""), business.get("address", "")
    phone_href = "tel:" + re.sub(r"[^0-9+]", "", str(phone))
    parts = [part.strip() for part in address.split(",")]
    location = ", ".join(parts[-3:-1]) if len(parts) >= 3 else ""
    location = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", location)
    is_tree = "tree" in name.lower()
    business_label = "Tree service" if is_tree else name
    phone_html = phone_link(phone)
    brand_initial = escape(name[:1].upper() if name else "B")
    address_html = f'<p class="address">{escape(str(address))}</p>' if address and not is_tree else ""
    directions = f'<a class="directions" href="https://maps.google.com/?{urlencode({"q": address})}" target="_blank" rel="noopener">Get directions ↗</a>' if address and not is_tree else ""
    if is_tree:
        facts = "".join(f"<div>{label}</div>" for label in ("Insured tree services", "North Raleigh · Wake Forest", "24/7 emergency & crane · North Raleigh"))
    else:
        facts = "".join(f'<div><strong>{escape(str(value))}</strong><span>{label}</span></div>' for value, label in ((business_label, "Business"), (location, "Location")) if value)
        if phone:
            digits = "".join(c for c in str(phone) if c.isdigit() or c == "+")
            facts += f'<div><a href="tel:{escape(digits)}"><strong>{escape(str(phone))}</strong><span>Call directly ↗</span></a></div>'

    services = content.get("services", [])
    service_html = "".join(
        f'<article><span class="eyebrow">{index:02d}</span><h3>{escape(str(item["name"]))}</h3>'
        f'<p>{escape(str(item.get("description", "")))}</p></article>'
        for index, item in enumerate(services, 1)
    )
    services_title = "Tree care from canopy to stump" if is_tree else f"Services from {escape(name)}"
    services_section = f'<section id="services" class="services scroll-reveal"><div class="service-heading"><p class="eyebrow">THE CARE</p><h2>{services_title}</h2></div><div class="service-grid">{service_html}</div></section>' if service_html else ""
    issue_section = f'''<section class="need-section"><p class="eyebrow">START WITH WHAT YOU’RE SEEING</p><h2>What needs attention?</h2><div class="need-grid"><article><p class="eyebrow">AFTER A STORM</p><h3>A tree or limb came down?</h3><p>Emergency tree and crane services are available 24/7 in the local North Raleigh area.</p><a href="{escape(phone_href, quote=True)}">Call about storm damage ↗</a></article><article><p class="eyebrow">MORE LIGHT</p><h3>Branches crowding your space?</h3><p>Tree trimming removes dead branches and can bring more light to your landscape and home.</p><a href="{escape(phone_href, quote=True)}">Ask about trimming ↗</a></article><article><p class="eyebrow">CLEAR THE STUMP</p><h3>Need the stump ground?</h3><p>The self-propelled grinder fits through a 36-inch gate and grinds stumps 6 inches below ground level.</p><a href="{escape(phone_href, quote=True)}">Ask about stump grinding ↗</a></article></div></section>''' if is_tree else ""
    tree_notes = f'''<section class="tree-notes"><div><p class="eyebrow">A USEFUL STARTING POINT</p><h2>Every tree has its own timing.</h2><p>Pruning timing can depend on the tree species, its condition, and the reason for pruning. Note what you’re seeing—dead branches, a need for more light, or a goal of supporting tree health and growth—then call to discuss the next step.</p>{phone_html}<small class="source">Timing guidance: <a href="https://content.ces.ncsu.edu/extension-gardener-handbook/11-woody-ornamentals" target="_blank" rel="noopener">NC State Extension</a></small></div><div class="tree-faq"><p class="eyebrow">COMMON QUESTIONS</p><details><summary>What can tree trimming help with?</summary><p>Brown’s describes trimming as a way to remove dead branches and bring more light to your landscape and home.</p></details><details><summary>What is tree pruning for?</summary><p>Brown’s offers pruning to support the health and growth of your trees.</p></details><details><summary>Not sure which one fits?</summary><p>Call Brown’s Tree Service and explain what you’d like to change.</p></details></div></section>''' if is_tree else ""
    website = research.get("pages", [{}])[0].get("url", business.get("website", "")) if research.get("pages") else business.get("website", "")
    website_html = f'<a href="{escape(str(website), quote=True)}" target="_blank" rel="noopener">Visit the business website ↗</a>' if website.startswith(("https://", "http://")) else ""
    photos = TREE_PHOTOS if is_tree else research.get("images", [])
    def photo(item, class_name, loading="lazy"):
        if not item:
            return ""
        alt = item.get("alt") or "Brown’s Tree Service project photo"
        return f'<img class="{class_name}" src="{escape(item["url"], quote=True)}" alt="{escape(alt, quote=True)}" loading="{loading}">'
    hero_image = photo(photos[0], "hero-image", "eager") if photos else ""
    hero_credit = f'<p class="hero-credit">Illustrative photo by <a href="{escape(photos[0]["source"], quote=True)}">{escape(photos[0]["credit"])}</a></p>' if is_tree else (f'<p class="hero-credit">Photo from <a href="{escape(str(website), quote=True)}">{escape(name)}</a></p>' if research.get("images") else "")
    about_photo = f'<div class="about-photo">{photo(photos[1] if len(photos) > 1 else photos[0], "about-image")}</div>' if photos else ""
    tree_gallery = "".join(f'<figure>{photo(item, "gallery-image")}<figcaption>{escape(item["alt"])} · <a href="{escape(item["source"], quote=True)}">{escape(item["credit"])}</a></figcaption></figure>' for item in photos[2:6]) if is_tree else ""
    gallery_section = f'<section class="field-notes"><p class="eyebrow">ON THE JOB</p><h2>Tree work, in the field.</h2><div class="photo-grid">{tree_gallery}</div></section>' if is_tree and tree_gallery else ""
    owner_section = f'<section class="owner-note"><div><p class="eyebrow">A PERSONAL ESTIMATE</p><h2>Craig Brown is on every job site.</h2></div><p>Estimates are given by owner/operator Craig Brown, who works on every job site.</p></section>' if is_tree else ""
    testimonials = research.get("testimonials", [])
    review_cards = "".join(f'<blockquote>“{escape(item["quote"])}”<cite>{escape(item["author"])} · Google review</cite></blockquote>' for item in testimonials if item.get("quote") and item.get("author"))
    reviews_url = research.get("testimonials_url", "")
    review_link = f'<a href="{escape(reviews_url, quote=True)}" target="_blank" rel="noopener">Read more customer stories ↗</a>' if reviews_url.startswith(("https://", "http://")) else ""
    reviews_section = f'<section class="reviews"><p class="eyebrow">FROM LOCAL CUSTOMERS</p><h2>Work that leaves a good impression.</h2><div class="review-grid">{review_cards}</div>{review_link}</section>' if is_tree and review_cards else ""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(name)}</title><link rel="stylesheet" href="styles.css"><script src="script.js" defer></script></head>
<body><header class="site-header"><a class="brand" href="#top"><span class="brand-mark">{brand_initial}</span>{escape(name)}</a>
<nav><a href="#services">Services</a><a href="#about">About</a><a href="#contact">Contact</a>{phone_html.replace('class="button primary"', 'class="nav-call"')}</nav></header>
<main id="top"><section class="hero">{hero_image}<div class="hero-copy"><p class="eyebrow">{escape(business_label)} · {escape(location)}</p>
<h1>{'Tree care,<br>from canopy<br>to stump.' if is_tree else escape(content['headline'])}</h1><p class="lead">{'Trimming, pruning, tree removal, stump grinding, and emergency tree & crane service across North Raleigh, Wake Forest, and nearby areas.' if is_tree else escape(content['subheadline'])}</p>{phone_html}</div>{hero_credit}</section>
<section class="facts" aria-label="Business details">{facts}</section>
<section id="about" class="about scroll-reveal">{about_photo}<div class="about-copy"><p class="eyebrow">{escape(business_label)} · {escape(location)}</p>
<h2>{'Clear dead branches. Let the light in.' if is_tree else escape(content['intro_title'])}</h2><p>{escape(content['intro'])}</p></div></section>
{issue_section}
{services_section}
{owner_section}
{gallery_section}
{reviews_section}
{tree_notes}
<section id="contact" class="contact"><p class="eyebrow">YOUR NEXT STEP · {escape(location)}</p><h2>{'What does your property need?' if is_tree else escape(content['cta_title'])}</h2><p>{'Call Brown’s Tree Service for trimming, removal, stump work, or emergency tree and crane service.' if is_tree else escape(content['cta_text'])}</p>
{phone_html}{address_html}{directions}{website_html}</section></main>
<footer><span>{escape(name)}</span><span>{escape(location)}</span></footer></body></html>"""
    for section in ("need-section", "owner-note", "field-notes", "reviews", "tree-notes", "contact"):
        html = html.replace(f'class="{section}"', f'class="{section} scroll-reveal"')
    return html

def generate_website(handoff_path):
    handoff_path = Path(handoff_path)

    handoff = load_json(handoff_path)

    business_path = (
        handoff_path.parent / "business.json"
    )

    if not business_path.exists():
        raise RuntimeError(
            "business.json not found."
        )

    business = load_json(
        business_path
    )

    reference_path = handoff_path.parent / "reference_analysis.json"
    design_spec = load_json(reference_path).get("design_spec", {}) if reference_path.exists() else {}

    research = load_or_research_business(handoff_path, business)
    if not research.get("pages"):
        raise RuntimeError(f"Could not read the supplied business website. See {handoff_path.parent / 'business_research.json'}; no DeepSeek request was made.")
    generated = generate_business_content(
        business,
        handoff,
        research,
    )
    content = verified_business_content(business, generated, research)
    content_path = handoff_path.parent / "business_content.json"
    content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    html = build_html(business, content, design_spec, research)

    output_dir = (
        handoff_path.parent / "website"
    )

    output_dir.mkdir(
        exist_ok=True
    )

    if "tree" in get_business_name(business, {}).lower():
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        for image in Path(__file__).parent.joinpath("assets", "tree_service").glob("*.jpeg"):
            shutil.copy2(image, images_dir / image.name)

    (output_dir / "index.html").write_text(
        html,
        encoding="utf-8",
    )

    (output_dir / "styles.css").write_text(
        css_for_design_spec(design_spec),
        encoding="utf-8",
    )

    (output_dir / "script.js").write_text(
        JS,
        encoding="utf-8",
    )

    (output_dir / "ELEMENTOR_REBUILD_NOTES.md").write_text(
        """# Elementor Rebuild Notes

Recreate the generated page's compact header, hero, business introduction,
supported services (if provided), and contact section. Keep the reference's
palette and typography. Do not add unsupported business claims.
""",
        encoding="utf-8",
    )

    return output_dir


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Generate premium local-business "
            "landing pages using DeepSeek."
        )
    )

    modes = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "ai_handoff",
        help="Path to AI_HANDOFF.json",
    )
    modes.add_argument(
        "--reference-analysis-only",
        action="store_true",
        help="Analyze one Admire The Web submission and save a design spec without rendering a website.",
    )
    modes.add_argument(
        "--content-only",
        action="store_true",
        help="Generate and save verified business website content without rendering a website.",
    )
    modes.add_argument(
        "--research-only",
        action="store_true",
        help="Crawl the supplied business website and save findings without using DeepSeek.",
    )

    args = parser.parse_args()

    if args.reference_analysis_only:
        result, label = generate_reference_analysis(args.ai_handoff), "Reference analysis saved"
    elif args.research_only:
        result, label = generate_research_only(args.ai_handoff), "Business research saved"
    elif args.content_only:
        result, label = generate_content_only(args.ai_handoff), "Business content saved"
    else:
        result, label = generate_website(args.ai_handoff), "Website created"
    print(f"\n{label}: {result}")
