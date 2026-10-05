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
STUMP_PHOTOS = [
    {"url": "https://images.pexels.com/photos/37038506/pexels-photo-37038506/free-photo-of-tree-stump-in-sunlit-garden-with-houses.jpeg?auto=compress&cs=tinysrgb&w=1800", "alt": "Tree stump in a residential garden; illustrative stock photo", "credit": "Pexels", "source": "https://www.pexels.com/search/stump%20grinder/"},
    {"url": "https://images.pexels.com/photos/9806894/pexels-photo-9806894.jpeg?auto=compress&cs=tinysrgb&w=1200", "alt": "Recently cut tree stump with sawdust; illustrative stock photo", "credit": "Pexels", "source": "https://www.pexels.com/search/stump%20grinder/"},
    {"url": "https://images.pexels.com/photos/15374402/pexels-photo-15374402/free-photo-of-tree-trunk-by-roadside.jpeg?auto=compress&cs=tinysrgb&w=1200", "alt": "Tree stump beside a neighborhood road; illustrative stock photo", "credit": "Pexels", "source": "https://www.pexels.com/search/stump%20grinder/"},
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
        elif tag == "link" and ("stylesheet" in attrs.get("rel", "").lower() or attrs.get("as", "").lower() == "style"):
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
        self.link_texts = []
        self.current_link = None
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"a", "article", "h1", "h2", "h3", "h4", "li", "p", "section"}:
            self.text.append("\n")
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
            self.current_link = []
        image_src = attrs.get("src") or attrs.get("data-src") or attrs.get("data-dm-image-path")
        if tag == "img" and image_src:
            self.images.append({"src": image_src, "alt": attrs.get("alt", "")[:120]})

    def handle_data(self, data):
        if self.skip:
            return
        clean = " ".join(data.split())
        if self.in_title and clean:
            self.title.append(clean)
        if clean:
            self.text.append(clean + " ")
            if self.current_link is not None:
                self.current_link.append(clean)
            if self.heading is not None:
                self.heading[1].append(clean)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            label = " ".join(self.current_link)
            if label:
                self.link_texts.append(label[:120])
            self.current_link = None
        if tag in {"a", "article", "h1", "h2", "h3", "h4", "li", "p", "section"}:
            self.text.append("\n")
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if self.heading is not None and tag == self.heading[0]:
            heading = " ".join(self.heading[1]).strip()
            if heading:
                self.headings.append(heading[:150])
            self.heading = None


def find_business_services(business_name, text):
    is_tree = "tree" in business_name
    is_stump = "stump" in business_name
    if is_tree:
        patterns = (
        ("Emergency Tree & Crane Services", r"\bemergency\b.{0,80}\b(?:tree|crane)"),
        ("Tree Removal Services", r"\btree removal\b"),
        ("Tree Trimming", r"\btrim(?:ming)?\b"),
        ("Tree Pruning", r"\bprun(?:e|ing)\b"),
        ("Stump Grinding & Removal Services", r"\bstump grind(?:ing)?\b"),
        ("Local Wood Chip Deliveries", r"\bwood chips?\b.{0,60}\bdeliver"),
        )
    elif is_stump:
        patterns = (
            ("Stump Grinding", r"\bstump grind(?:ing)?\b"),
            ("Stump Removal", r"\bstump remov(?:al|e)\b"),
        )
    else:
        patterns = ()
    sentences = re.split(r"(?<=[.!?])\s+|\s*[\r\n]+\s*", text)
    found = {}
    for label, pattern in patterns:
        matches = [sentence for sentence in sentences if re.search(pattern, sentence, re.I)]
        if matches:
            found[label] = " ".join(dict.fromkeys(matches))[:280]
    if not (is_tree or is_stump):
        service_phrase = re.compile(r"\b(?:[a-z0-9&/-]+\s+){0,3}(?:services?|repairs?|installations?|replacements?|cleaning|testing|inspections?|maintenance|pumps?|lines?|jetting|repiping|heaters?|pipes?|plumbing)\b", re.I)
        for sentence in sentences:
            if len(sentence) > 100:
                continue
            for match in service_phrase.finditer(sentence):
                words = re.sub(r"\s+", " ", match.group()).strip(" ,.-").split()
                verbs = {"provides", "provide", "offers", "offer", "including", "include", "contact", "book", "call", "and", "or", "with", "you", "we", "need", "turn", "not", "a", "our", "either", "on", "see", "all", "residential", "require", "requires", "fails", "failed", "if", "pass", "restore", "assembly", "handles", "handle"}
                if any(word.lower() in verbs for word in words):
                    words = words[max(i for i, word in enumerate(words) if word.lower() in verbs) + 1:]
                label = " ".join(words).title()
                if not label or label.lower() in {"service", "services", "repair", "repairs", "installation", "inspection", "our services", "reviews blog our services", "emergency services", "commercial services", "residential services"} or label.lower().endswith(" emergency services"):
                    continue
                canonical = re.sub(r"\b(certified|residential|commercial|local)\b", "", label.lower()).strip()
                if any(re.sub(r"\b(certified|residential|commercial|local)\b", "", old.lower()).strip() == canonical for old in found):
                    continue
                found.setdefault(label, sentence[:280])
    return found


def css_color_hex(value):
    if value.startswith("#"):
        value = value.upper()
        return "#" + "".join(ch * 2 for ch in value[1:]) if len(value) == 4 else value if len(value) == 7 else None
    channels = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?", value, re.I)
    if not channels or (channels.group(4) is not None and float(channels.group(4)) == 0):
        return None
    return "#" + "".join(f"{min(255, int(channels.group(i))):02X}" for i in (1, 2, 3))


def extract_brand_palette(html, page_url):
    page = PageParser()
    page.feed(html)
    css = " ".join(page.styles)
    for stylesheet in page.stylesheets[:5]:
        try:
            stylesheet_text, _ = fetch_page(urljoin(page_url, stylesheet), limit=500_000, timeout=8)
            css += " " + stylesheet_text
        except (HTTPError, URLError, RuntimeError, TimeoutError, OSError):
            continue

    variables = {}
    for number, raw in re.findall(r"--color_(\d+)\s*:\s*(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|rgba?\([^)]{1,80}\))", css, re.I):
        color = css_color_hex(raw)
        if color:
            variables.setdefault(number, color)
    if variables:
        roles = {"primary": "1", "secondary": "2", "accent": "4", "background": "6", "surface": "7", "text": "8"}
        return {role: variables[number] for role, number in roles.items() if number in variables}

    counts = Counter(
        color for raw in re.findall(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|rgba?\([^)]{1,80}\)", css, re.I)
        if (color := css_color_hex(raw))
    )
    colors = [color for color, _ in counts.most_common()]
    neutral = [color for color in colors if max(int(color[i:i + 2], 16) for i in (1, 3, 5)) - min(int(color[i:i + 2], 16) for i in (1, 3, 5)) < 24]
    vivid = [color for color in colors if color not in neutral]
    brightness = lambda color: sum(int(color[i:i + 2], 16) for i in (1, 3, 5))
    light = sorted((color for color in neutral if brightness(color) > 560), key=brightness, reverse=True)
    dark = sorted((color for color in neutral if brightness(color) < 420), key=brightness)
    return {
        key: value for key, value in {
            "primary": vivid[0] if vivid else None,
            "secondary": vivid[1] if len(vivid) > 1 else None,
            "accent": vivid[2] if len(vivid) > 2 else vivid[0] if vivid else None,
            "background": light[0] if light else None,
            "surface": light[1] if len(light) > 1 else light[0] if light else None,
            "text": dark[0] if dark else None,
        }.items() if value
    }


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
    pages, services, images, errors, seen, seen_pages = [], [], [], [], set(), set()
    brand_palette = {}
    business_name = re.sub(r"[^a-z0-9]+", "", str(business.get("business_name", "")).lower())
    is_tree = "tree" in business_name
    is_stump = "stump" in business_name
    service_details = {}

    while queue and len(pages) < 3:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            # ponytail: cap each business page at 2 MB; this site's homepage is about 1.4 MB.
            html, final_url = fetch_page(url, limit=2_000_000, timeout=12)
        except HTTPError as error:
            errors.append({"type": "HTTPError", "status": error.code})
            continue
        except (URLError, RuntimeError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            errors.append({"type": type(error).__name__, "reason_type": type(reason).__name__})
            continue
        page = BusinessPageParser()
        page.feed(html)
        if not brand_palette:
            brand_palette = extract_brand_palette(html, final_url)
        page_key = final_url.split("?", 1)[0].rstrip("/").lower()
        if page_key in seen_pages:
            continue
        seen.add(final_url)
        seen_pages.add(page_key)
        page_text = re.sub(r"\n+", "\n", re.sub(r"[ \t]+", " ", "".join(page.text))).strip()
        pages.append({
            "url": final_url,
            "title": " ".join(page.title)[:160],
            "description": page.description,
            "headings": page.headings[:24],
            "text": page_text[:3500],
        })
        service_text = pages[-1]["text"] if is_tree or is_stump else "\n".join(page.link_texts)
        details = find_business_services(business_name, service_text)
        service_path = urlparse(final_url).path.lower()
        if not (is_tree or is_stump) and re.search(r"service|solution|product|offering|capabilit|what[-_]we[-_]do|specialt|treatment", service_path):
            ignored_headings = {"services", "our services", "all services", "what we do", "solutions", "our solutions", "products", "about us", "contact", "reviews", "testimonials", "faq", "frequently asked questions"}
            for heading in page.headings:
                label = re.sub(r"\s+", " ", heading).strip(" .:-")
                if not 3 <= len(label) <= 80 or label.casefold() in ignored_headings:
                    continue
                excerpt = next((sentence for sentence in re.split(r"(?<=[.!?])\s+|\s*[\r\n]+\s*", pages[-1]["text"]) if label.casefold() in sentence.casefold()), "Listed on the business's own service page.")
                details.setdefault(label, excerpt[:280])
        services.extend(details)
        service_details.update(details)
        for image in page.images:
            image_url = urljoin(final_url, image["src"])
            if image_url.startswith(("https://", "http://")) and not re.search(r"logo|icon|badge|star|facebook|google", image["src"] + image["alt"], re.I) and image_url not in {item["url"] for item in images}:
                images.append({"url": image_url, "alt": image["alt"]})
        candidates = []
        for link in page.links:
            candidate = urljoin(final_url, link).split("#", 1)[0]
            parts = urlparse(candidate)
            if parts.scheme not in ("http", "https") or (parts.hostname or "").removeprefix("www.") != host or candidate in seen:
                continue
            path = parts.path.lower()
            score = sum(word in path for word in ("service", "tree", "about", "emergency", "contact", "stump", "crane", "residential", "commercial", "backflow", "plumb", "drain", "water", "heater", "solution", "product", "offering", "capabilit", "what-we-do", "specialt", "treatment"))
            if score:
                candidates.append((score, candidate))
        queue.extend(url for _, url in sorted(set(candidates), reverse=True))

    if not pages:
        search_terms = "tree removal trimming pruning emergency crane stump grinding" if is_tree else "stump grinding stump removal estimate" if is_stump else "services"
        results, search_error = tavily_search(f'site:{host} "{business.get("business_name", "")}" {search_terms}', host)
        for result in results:
            result_host = (urlparse(result["url"]).hostname or "").removeprefix("www.")
            if result_host != host:
                continue
            text = " ".join([result.get("description", ""), *result.get("snippets", [])]).strip()
            pages.append({"url": result["url"], "title": result["title"], "description": result.get("description", ""), "headings": [result["title"]], "text": text[:1800], "source_type": "first-party search result"})
            details = find_business_services(business_name, text)
            services.extend(details)
            service_details.update(details)
        errors.append({"type": "TavilySearch", "reason": search_error} if search_error else {"type": "TavilySearch", "results": len(pages)})

    return {
        "business_website": website,
        "pages": pages,
        "services": list(dict.fromkeys(services))[:15],
        "service_details": service_details,
        "images": images[:12],
        "brand_palette": brand_palette,
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


def discover_reference(reference_index=0):
    gallery_html, _ = fetch_page(ADMIRE_URL)
    gallery = GalleryParser()
    gallery.feed(gallery_html)
    ignored_hosts = {"admiretheweb.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "google.com", "feedburner.com", "linkedin.com", "pinterest.com", "youtube.com", "tiktok.com"}
    references = []
    for item in gallery.items:
        detail_html, detail_url = fetch_page(urljoin(ADMIRE_URL, item["url"]))
        links = LinkParser()
        links.feed(detail_html)
        for href in links.urls:
            candidate = urljoin(detail_url, href)
            parsed = urlparse(candidate)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            if parsed.scheme in ("http", "https") and host and not any(host == blocked or host.endswith("." + blocked) for blocked in ignored_hosts) and not parsed.path.startswith("/intent/"):
                references.append({"name": item["name"] or host, "url": candidate})
                break
        if len(references) > reference_index:
            return references[reference_index]
    raise RuntimeError(f"Admire The Web has no submitted website at reference index {reference_index}.")


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


DESIGN_DIRECTOR_PROMPT = """Create an original, implementable design_spec for the supplied business using the supplied reference_analysis. Transfer visual principles only; copy no brand, text, or assets; invent no business claims. Return only JSON with exactly these keys: layout, header, hero, typography, palette, spacing, components, imagery, section_composition, visual_hierarchy. Keep each text value to 8 words maximum; palette is an array of up to 5 CSS colors."""


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


def generate_reference_analysis(handoff_path, reference_index=0):
    handoff_path = Path(handoff_path)
    business = load_json(handoff_path.parent / "business.json")
    reference = discover_reference(reference_index)
    analysis = analyze_reference(reference)
    spec, usage = create_design_spec(business, reference, analysis)
    artifact = {"business": business.get("business_name") or "Local Business", "reference": reference, "reference_analysis": analysis, "design_spec": spec}
    output = handoff_path.parent / "reference_analysis.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        log_usage(artifact["business"], usage)
    except Exception as error:
        print(f"Usage logging skipped: {error}")
    return output


SYSTEM_PROMPT = """Write specific website copy from the supplied business facts and research. Research is the source of truth: do not invent claims, ratings, years, credentials, prices, guarantees, services, or customer stories. List only supplied services and describe only supported details. Return JSON with exactly: headline, subheadline, intro_title, intro, services (up to 6 objects with exact supplied name and grounded description), proof_points (up to 3 grounded title/text objects), cta_title, cta_text. Keep it concise and natural."""


CSS = r"""
:root { --bg: __BG__; --text: __TEXT__; --muted: color-mix(in srgb,__TEXT__ 66%,__BG__); --gold: __ACCENT__; --gold-light: __WARM__; --brand: __BRAND__; --secondary: __SECONDARY__; --on-accent: __ON_ACCENT__; --surface: __SURFACE__; --line: color-mix(in srgb,__TEXT__ 14%,transparent); --max: 1240px; }
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
.button:hover { transform:translateY(-2px); background:#ead49b; color:var(--brand); }
.facts { display:flex; flex-wrap:wrap; justify-content:center; gap:16px 44px; margin:auto; padding:22px 5%; background:#1d3828; color:#f8f5eb; text-align:center; }
.facts div { display:flex; flex-direction:column; gap:3px; min-width:120px; font-size:.76rem; font-weight:700; letter-spacing:.04em; }
.facts div span { color:#ffffffb8; font-size:.64rem; letter-spacing:.1em; text-transform:uppercase; }
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
.photo-grid.single-photo { grid-template-columns:minmax(0,1fr); grid-template-rows:minmax(220px,420px); }
.photo-grid.single-photo figure:first-child { grid-column:auto; grid-row:auto; }
.photo-grid img { width:100%; height:100%; object-fit:cover; transition:transform .35s; }
.photo-grid figure:hover img { transform:scale(1.04); }
.photo-grid figcaption { position:absolute; inset:auto 0 0; padding:24px 14px 12px; color:white; font-size:.76rem; background:linear-gradient(transparent,#0c1711cc); }
.about.text-only { display:block; max-width:850px; }
.about.text-only .about-copy > p:last-child { max-width:700px; }
.scroll-reveal.is-visible .about-photo,.scroll-reveal.is-visible .need-grid article,.scroll-reveal.is-visible .service-grid article,.scroll-reveal.is-visible .photo-grid figure,.scroll-reveal.is-visible .review-grid blockquote,.scroll-reveal.is-visible.contact { animation:reveal-up .65s cubic-bezier(.2,.75,.2,1) both; }
.scroll-reveal.is-visible .need-grid article:nth-child(2),.scroll-reveal.is-visible .service-grid article:nth-child(2),.scroll-reveal.is-visible .photo-grid figure:nth-child(2),.scroll-reveal.is-visible .review-grid blockquote:nth-child(2) { animation-delay:.12s; }
.scroll-reveal.is-visible .need-grid article:nth-child(3),.scroll-reveal.is-visible .service-grid article:nth-child(3),.scroll-reveal.is-visible .photo-grid figure:nth-child(3) { animation-delay:.24s; }
@keyframes reveal-up { from { opacity:.72; transform:translateY(18px); } to { opacity:1; transform:none; } }
.reviews { max-width:var(--max); margin:0 auto; padding:0 5% 100px; }
.review-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }
.review-grid blockquote { margin:0; padding:26px 28px; border-left:2px solid #d8b663; background:transparent; font-family:Georgia,'Times New Roman',serif; font-size:1.45rem; line-height:1.45; }
.review-grid cite { display:block; margin-top:20px; color:var(--muted); font:600 .74rem system-ui,sans-serif; letter-spacing:.08em; text-transform:uppercase; }
.reviews > a { display:inline-block; margin-top:18px; text-decoration:underline; text-underline-offset:4px; }
.contact { max-width:calc(var(--max) - 10%); margin:0 auto 78px; padding:58px 7%; display:flex; flex-wrap:wrap; align-items:center; gap:12px 36px; background:#1f3829; color:white; border-radius:3px; }
.contact .eyebrow { width:100%; color:#d9e4b0; margin:0; }
.contact h2 { flex:1 1 420px; margin:0; font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.2rem,5vw,4.1rem); line-height:1; letter-spacing:-.045em; font-weight:500; }
.contact > p:not(.eyebrow) { flex:1 1 250px; color:#ffffffc9; }
.contact .button { background:#d8b663; color:#17291e; }
.contact > a:not(.button) { flex-basis:100%; margin:0; color:#ffffffd9; text-decoration:underline; text-underline-offset:4px; }
footer { max-width:var(--max); margin:auto; padding:24px 5%; display:flex; justify-content:space-between; gap:20px; border-top:1px solid var(--line); color:var(--muted); font-size:.85rem; }
@media(max-width:980px) { .service-grid { grid-template-columns:repeat(2,1fr); } .photo-grid { grid-template-columns:repeat(2,1fr); grid-template-rows:190px 190px; } .photo-grid figure:first-child,.photo-grid figure:nth-child(3) { grid-column:auto; grid-row:auto; } }
@media(max-width:720px) { .site-header { height:76px; margin-bottom:-76px; padding:0 6%; } section[id] { scroll-margin-top:90px; } .site-header nav { gap:14px; font-size:.8rem; } .site-header nav a:not(.nav-call) { display:none; } .hero { min-height:700px; padding:120px 7% 75px; } .hero-copy { padding-left:18px; } .hero h1 { font-size:clamp(3.6rem,15vw,6rem); } .facts { gap:12px 20px; padding:18px 6%; } .facts div { font-size:.68rem; } .about { padding:72px 6%; grid-template-columns:1fr; gap:30px; } .about-photo { height:300px; } .need-section { padding:0 6% 72px; } .need-grid { grid-template-columns:1fr; gap:10px; } .need-grid article { min-height:0; padding:20px 0; } .services { padding:58px 6% 72px; } .service-grid,.review-grid { grid-template-columns:1fr; gap:12px; } .service-grid article { min-height:0; padding:22px 0; } .field-notes,.reviews { padding:0 6% 72px; } .photo-grid { grid-template-columns:1fr 1fr; grid-template-rows:none; gap:8px; } .photo-grid figure,.photo-grid figure:first-child,.photo-grid figure:nth-child(3) { grid-column:auto; grid-row:auto; height:190px; } .photo-grid.single-photo { grid-template-columns:1fr; grid-template-rows:240px; } .photo-grid.single-photo figure { height:240px; } .contact { margin:0 6% 48px; padding:38px 28px; } footer { padding:22px 6%; flex-direction:column; gap:5px; } }
@media(prefers-reduced-motion:reduce) { html { scroll-behavior:auto; } *,*::before,*::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; } }
"""

def css_for_design_spec(design_spec, brand_palette=None):
    defaults = {"BG": "#F5F0E6", "TEXT": "#1A1A1A", "SURFACE": "#FFFFFF", "ACCENT": "#3E5C3A", "WARM": "#8B6F47", "BRAND": "#1D3828", "SECONDARY": "#3E5C3A", "ON_ACCENT": "#FFFFFF"}
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

    defaults["BRAND"] = defaults["ACCENT"]
    defaults["SECONDARY"] = defaults["WARM"]
    if brand_palette:
        defaults["BG"] = brand_palette.get("background", defaults["BG"])
        defaults["TEXT"] = brand_palette.get("text", defaults["TEXT"])
        defaults["SURFACE"] = brand_palette.get("surface", defaults["SURFACE"])
        defaults["BRAND"] = brand_palette.get("primary", defaults["BRAND"])
        defaults["ACCENT"] = brand_palette.get("secondary", defaults["ACCENT"])
        defaults["SECONDARY"] = brand_palette.get("accent", defaults["SECONDARY"])
        defaults["WARM"] = defaults["SECONDARY"]
    rgb = channels(defaults["ACCENT"])
    defaults["ON_ACCENT"] = "#FFFFFF" if sum(rgb) < 390 else "#101010"

    css = CSS
    for color, variable in {
        "#d8b663": "var(--gold)", "#ead49b": "var(--gold-light)", "#e6ce93": "var(--gold-light)",
        "#a8c28e": "var(--gold-light)", "#d9e4b0": "var(--gold-light)", "#1d3828": "var(--brand)",
        "#1f3829": "var(--brand)", "#15271d": "var(--brand)", "#17291e": "var(--on-accent)",
        "#e9e7d9": "var(--surface)", "rgba(15,31,22,.78)": "color-mix(in srgb,var(--brand) 86%,transparent)",
        "rgba(8,23,15,.92)": "color-mix(in srgb,var(--brand) 92%,transparent)",
        "rgba(8,23,15,.68)": "color-mix(in srgb,var(--brand) 68%,transparent)",
        "rgba(8,23,15,.45)": "color-mix(in srgb,var(--brand) 45%,transparent)",
        "rgba(8,23,15,.1)": "color-mix(in srgb,var(--brand) 10%,transparent)",
        "#0f1712b8": "color-mix(in srgb,var(--brand) 72%,transparent)",
        "#0c1711cc": "color-mix(in srgb,var(--brand) 80%,transparent)",
    }.items():
        css = css.replace(color, variable)
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
    first_service = next(iter(research.get("services", [])), "")
    fallback = {
        "headline": f"{first_service} in {location}" if first_service and location else name,
        "subheadline": f"{name} · {location}" if location else name,
        "intro_title": f"About {name}",
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
        and len(normalize(item.get("description", ""))) > len(normalize(item.get("name", ""))) + 12
    ]
    included = {normalize(item["name"]) for item in content["services"]}
    content["services"].extend(
        {"name": name, "description": str(research.get("service_details", {}).get(name, ""))[:280]}
        for name in research.get("services", [])
        if normalize(name) not in included and research.get("service_details", {}).get(name)
        and len(normalize(research["service_details"][name])) > len(normalize(name)) + 12
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
    content = content or {}
    name = get_business_name(business, {})
    phone, address = business.get("phone", ""), business.get("address", "")
    phone_href = "tel:" + re.sub(r"[^0-9+]", "", str(phone))
    parts = [part.strip() for part in address.split(",")]
    location = ", ".join(parts[-3:-1]) if len(parts) >= 3 else ""
    location = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", location)
    is_tree = "tree" in name.lower()
    is_stump = "stump" in name.lower()
    phone_html = phone_link(phone)
    brand_initial = escape(name[:1].upper() if name else "B")
    address_html = f'<p class="address">{escape(str(address))}</p>' if address else ""
    directions = f'<a class="directions" href="https://maps.google.com/?{urlencode({"q": address})}" target="_blank" rel="noopener">Get directions ↗</a>' if address else ""
    facts = "".join(
        f'<div><strong>{escape(value)}</strong><span>{label}</span></div>'
        for value, label in ((name, "Business"), (location, "Location"), (str(phone), "Call directly ↗")) if value
    )

    services = [item for item in content.get("services", []) if isinstance(item, dict) and item.get("name")]
    service_html = "".join(
        f'<article><span class="eyebrow">{index:02d}</span><h3>{escape(str(item["name"]))}</h3>'
        f'<p>{escape(str(item.get("description", "")))}</p></article>'
        for index, item in enumerate(services, 1)
    )
    services_title = "How we can help"
    services_section = f'<section id="services" class="services scroll-reveal"><div class="service-heading"><p class="eyebrow">SERVICES</p><h2>{services_title}</h2></div><div class="service-grid">{service_html}</div></section>' if service_html else ""
    proof_points = [item for item in content.get("proof_points", []) if isinstance(item, dict) and item.get("title") and item.get("text")]
    proof_html = "".join(f'<article><p class="eyebrow">{index:02d}</p><h3>{escape(str(item["title"]))}</h3><p>{escape(str(item["text"]))}</p></article>' for index, item in enumerate(proof_points, 1))
    proof_section = f'<section class="need-section scroll-reveal"><p class="eyebrow">WHY PEOPLE CALL</p><h2>The details that matter.</h2><div class="need-grid">{proof_html}</div></section>' if proof_html else ""
    website = business.get("website", "")
    website_html = f'<a href="{escape(str(website), quote=True)}" target="_blank" rel="noopener">Visit the business website ↗</a>' if website.startswith(("https://", "http://")) else ""
    photos = research.get("images", []) or (TREE_PHOTOS if is_tree else STUMP_PHOTOS if is_stump else [])
    def photo(item, class_name, loading="lazy"):
        if not item:
            return ""
        alt = item.get("alt") or f"Photo of {name}"
        return f'<img class="{class_name}" src="{escape(item["url"], quote=True)}" alt="{escape(alt, quote=True)}" loading="{loading}">'
    hero_image = photo(photos[0], "hero-image", "eager") if photos else ""
    image_source = photos[0].get("source", website)
    image_credit = photos[0].get("credit", "Business website photo" if research.get("images") else "Illustrative photo")
    hero_credit = f'<p class="hero-credit">{escape(image_credit)} · <a href="{escape(str(image_source), quote=True)}">Source</a></p>' if photos else ""
    about_photo = f'<div class="about-photo">{photo(photos[1] if len(photos) > 1 else photos[0], "about-image")}</div>' if photos else ""
    gallery = "".join(
        f'<figure>{photo(item, "gallery-image")}<figcaption>{escape(item.get("alt", "Project photo"))} · {escape(item.get("credit", "Business website photo"))}</figcaption></figure>'
        for item in photos[2:6]
    )
    gallery_class = "photo-grid single-photo" if len(photos[2:6]) == 1 else "photo-grid"
    gallery_section = f'<section class="field-notes scroll-reveal"><p class="eyebrow">IN PICTURES</p><h2>A closer look.</h2><div class="{gallery_class}">{gallery}</div></section>' if gallery else ""
    testimonials = research.get("testimonials", [])
    review_cards = "".join(f'<blockquote>“{escape(item["quote"])}”<cite>{escape(item["author"])} · Customer review</cite></blockquote>' for item in testimonials if isinstance(item, dict) and item.get("quote") and item.get("author"))
    reviews_url = research.get("testimonials_url", "")
    review_link = f'<a href="{escape(reviews_url, quote=True)}" target="_blank" rel="noopener">Read more customer stories ↗</a>' if reviews_url.startswith(("https://", "http://")) else ""
    reviews_section = f'<section class="reviews scroll-reveal"><p class="eyebrow">CUSTOMER FEEDBACK</p><h2>From people who know their work.</h2><div class="review-grid">{review_cards}</div>{review_link}</section>' if review_cards else ""
    nav_services = '<a href="#services">Services</a>' if services_section else ""
    nav_about = '<a href="#about">About</a>'
    text_only = " text-only" if not about_photo else ""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(name)}</title><link rel="stylesheet" href="styles.css"><script src="script.js" defer></script></head>
<body><header class="site-header"><a class="brand" href="#top"><span class="brand-mark">{brand_initial}</span>{escape(name)}</a>
<nav>{nav_services}{nav_about}<a href="#contact">Contact</a>{phone_html.replace('class="button primary"', 'class="nav-call"')}</nav></header>
<main id="top"><section class="hero">{hero_image}<div class="hero-copy"><p class="eyebrow">{escape(name)}{f' · {escape(location)}' if location else ''}</p>
<h1>{escape(content.get('headline') or name)}</h1><p class="lead">{escape(content.get('subheadline') or content.get('intro', ''))}</p>{phone_html}</div>{hero_credit}</section>
<section class="facts" aria-label="Business details">{facts}</section>
<section id="about" class="about scroll-reveal{text_only}">{about_photo}<div class="about-copy"><p class="eyebrow">ABOUT {escape(name.upper())}</p>
<h2>{escape(content.get('intro_title') or name)}</h2><p>{escape(content.get('intro') or content.get('subheadline', ''))}</p></div></section>
{proof_section}
{services_section}
{gallery_section}
{reviews_section}
<section id="contact" class="contact scroll-reveal"><p class="eyebrow">YOUR NEXT STEP{f' · {escape(location)}' if location else ''}</p><h2>{escape(content.get('cta_title') or f'Talk with {name}')}</h2><p>{escape(content.get('cta_text') or (f'Call {phone} to discuss your needs.' if phone else f'Contact {name} to discuss your needs.'))}</p>
{phone_html}{address_html}{directions}{website_html}</section></main>
<footer><span>{escape(name)}</span><span>{escape(location)}</span></footer></body></html>"""
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
        css_for_design_spec(design_spec, research.get("brand_palette")),
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
    parser.add_argument(
        "--reference-index",
        type=int,
        default=0,
        help="Choose a different Admire The Web submission (0 is the first).",
    )

    args = parser.parse_args()

    if args.reference_analysis_only:
        if args.reference_index < 0:
            parser.error("--reference-index must be 0 or greater")
        result, label = generate_reference_analysis(args.ai_handoff, args.reference_index), "Reference analysis saved"
    elif args.research_only:
        result, label = generate_research_only(args.ai_handoff), "Business research saved"
    elif args.content_only:
        result, label = generate_content_only(args.ai_handoff), "Business content saved"
    else:
        result, label = generate_website(args.ai_handoff), "Website created"
    print(f"\n{label}: {result}")
