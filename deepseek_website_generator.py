import argparse
import json
import os
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from api_usage_logger import log_usage


load_dotenv()

MODEL = "deepseek-chat"


SYSTEM_PROMPT = """
You are a senior local SEO strategist and conversion copywriter.

Create a SMALL JSON object containing business-specific website copy for a local
junk removal company.

Use ONLY information provided in the source data.

NEVER invent:
reviews, ratings, testimonials, awards, certifications, licenses,
years in business, customer counts, guarantees, pricing, discounts,
statistics, staff, locations, service areas, business hours, or unsupported claims.

If information is missing, do not state it as fact.

The goal is natural, useful, conversion-focused local SEO content.

Return ONLY valid JSON with exactly these keys:

{
  "headline": "",
  "subheadline": "",
  "intro": "",
  "about_title": "",
  "about": "",
  "services_intro": "",
  "services": [],
  "benefits": [],
  "process": [
    {"title": "", "text": ""},
    {"title": "", "text": ""},
    {"title": "", "text": ""}
  ],
  "local_intro": "",
  "faq": [
    {"question": "", "answer": ""}
  ],
  "cta_title": "",
  "cta_text": ""
}

CONTENT RULES:

HEADLINE:
- Under 12 words.
- Relevant to junk removal.
- Include the business name when natural.

SUBHEADLINE:
- Under 30 words.
- Clearly explain the local service.

INTRO:
- 80–120 words.
- Naturally mention junk removal.
- Mention the verified location when available.
- No keyword stuffing.

ABOUT:
- 100–150 words.
- Explain the value of the business.
- Never invent company history.

SERVICES:
Only include services explicitly supported by the supplied information.

Do NOT automatically add:
residential junk removal, commercial junk removal, furniture removal,
appliance removal, construction debris, yard waste, estate cleanouts,
garage cleanouts, hot tub removal, foreclosure cleanouts, or disposal
unless the source supports them.

Each service:
{
  "name": "",
  "description": ""
}

BENEFITS:
Create 4 short benefit statements based only on verified information
or reasonable non-factual service framing.

PROCESS:
Create:
1. Contact
2. Schedule
3. Removal

Keep the process general.

LOCAL SEO:
Naturally use the verified city, state and address.

Never create fake cities, neighborhoods or service areas.

FAQ:
Create up to 5 useful questions.
Answers must remain supported by the source.

Use natural keyword variations such as:
junk removal,
junk removal service,
local junk removal,
residential junk removal,
commercial junk removal,
furniture removal,
debris removal

ONLY when supported.

Avoid keyword stuffing.

Never use unsupported claims like:
best, #1, top-rated, cheapest, most trusted, fastest, guaranteed.

Do not mention AI, LeadFinder, Wolf Forge or internal processes.

Return ONLY JSON.
"""


CSS = r"""
:root {
    --bg: #07111f;
    --bg-soft: #0d1b2e;
    --card: #101f33;
    --text: #f7f9fc;
    --muted: #aeb9c9;
    --gold: #d7b56d;
    --gold-light: #f1d99a;
    --border: rgba(255,255,255,.12);
    --max: 1180px;
}

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    color: var(--text);
    background: var(--bg);
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.6;
}

a {
    color: inherit;
    text-decoration: none;
}

.container {
    width: min(92%, var(--max));
    margin: auto;
}

.header {
    position: sticky;
    top: 0;
    z-index: 10;
    border-bottom: 1px solid var(--border);
    background: rgba(7,17,31,.94);
    backdrop-filter: blur(12px);
}

.nav {
    min-height: 76px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 25px;
}

.logo {
    max-width: 300px;
    font-size: 19px;
    font-weight: 900;
}

nav {
    display: flex;
    gap: 24px;
}

nav a {
    color: var(--muted);
    font-size: 14px;
}

nav a:hover,
nav a:focus {
    color: var(--text);
}

.button {
    min-height: 50px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 23px;
    border-radius: 7px;
    font-weight: 900;
    transition: .2s ease;
}

.button:hover,
.button:focus {
    transform: translateY(-2px);
}

.primary {
    background: var(--gold);
    color: #07111f;
    box-shadow: 0 15px 35px rgba(215,181,109,.18);
}

.secondary {
    border: 1px solid var(--border);
    background: rgba(255,255,255,.04);
}

.hero {
    position: relative;
    overflow: hidden;
    min-height: 700px;
    display: flex;
    align-items: center;
    background:
        radial-gradient(
            circle at 80% 30%,
            rgba(215,181,109,.18),
            transparent 28%
        ),
        radial-gradient(
            circle at 15% 85%,
            rgba(39,93,150,.25),
            transparent 35%
        ),
        linear-gradient(135deg,#07111f,#0c1c31);
}

.hero-pattern {
    position: absolute;
    width: 600px;
    height: 600px;
    right: -250px;
    top: 50px;
    border: 1px solid rgba(215,181,109,.2);
    border-radius: 50%;
    box-shadow:
        0 0 0 80px rgba(215,181,109,.025),
        0 0 0 160px rgba(215,181,109,.018);
}

.hero-grid {
    position: relative;
    display: grid;
    grid-template-columns: 1.1fr .9fr;
    gap: 70px;
    align-items: center;
}

.hero-content {
    position: relative;
}

.eyebrow {
    display: inline-block;
    margin-bottom: 18px;
    color: var(--gold);
    font-size: 12px;
    font-weight: 900;
    letter-spacing: .18em;
}

h1 {
    max-width: 850px;
    margin: 0;
    font-size: clamp(48px,7vw,86px);
    line-height: .98;
    letter-spacing: -.06em;
}

h2 {
    margin: 0;
    font-size: clamp(34px,5vw,58px);
    line-height: 1.05;
    letter-spacing: -.05em;
}

h3 {
    margin: 0;
    font-size: 21px;
}

.hero-copy {
    max-width: 700px;
    margin: 30px 0;
    color: var(--muted);
    font-size: 20px;
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
}

.location {
    margin-top: 25px;
    color: var(--muted);
}

.hero-visual {
    position: relative;
    min-height: 430px;
}

.visual-main,
.visual-small {
    position: absolute;
    border: 1px solid var(--border);
    border-radius: 22px;
    background: linear-gradient(
        145deg,
        rgba(255,255,255,.11),
        rgba(255,255,255,.025)
    );
    box-shadow: 0 30px 80px rgba(0,0,0,.35);
}

.visual-main {
    inset: 20px 30px 70px 0;
    padding: 45px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.visual-main span {
    color: var(--muted);
    font-size: 30px;
    font-weight: 900;
}

.visual-main strong {
    color: var(--gold);
    font-size: clamp(55px,6vw,82px);
    line-height: .9;
}

.visual-small {
    right: 0;
    bottom: 0;
    padding: 23px;
    color: var(--gold-light);
    font-size: 13px;
    font-weight: 900;
    letter-spacing: .08em;
}

.intro-section {
    padding: 95px 0;
    border-bottom: 1px solid var(--border);
}

.intro-grid,
.local-grid {
    display: grid;
    grid-template-columns: .8fr 1.2fr;
    gap: 80px;
    align-items: center;
}

.intro-copy,
.local-copy {
    color: var(--muted);
    font-size: 20px;
    line-height: 1.8;
}

.section {
    padding: 115px 0;
}

.section-heading {
    max-width: 820px;
}

.section-heading p {
    margin-top: 22px;
    color: var(--muted);
    font-size: 18px;
}

.service-grid {
    display: grid;
    grid-template-columns: repeat(2,1fr);
    gap: 18px;
    margin-top: 50px;
}

.service-card {
    min-height: 250px;
    padding: 35px;
    border: 1px solid var(--border);
    border-radius: 18px;
    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.08),
            rgba(255,255,255,.025)
        );
    transition: transform .25s ease,border-color .25s ease;
}

.service-card:hover {
    transform: translateY(-5px);
    border-color: rgba(215,181,109,.45);
}

.service-number {
    color: var(--gold);
    font-weight: 900;
    letter-spacing: .1em;
}

.service-card h3 {
    margin-top: 75px;
}

.service-card p,
.process-card p {
    color: var(--muted);
}

.dark {
    background: var(--bg-soft);
}

.about-grid {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 60px;
}

.about-number {
    color: rgba(215,181,109,.15);
    font-size: 100px;
    font-weight: 900;
    line-height: 1;
}

.large-copy {
    max-width: 820px;
    color: var(--muted);
    font-size: 21px;
    line-height: 1.8;
}

.benefit-grid {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    gap: 16px;
    margin-top: 50px;
}

.benefit-card {
    min-height: 190px;
    padding: 28px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    border: 1px solid var(--border);
    border-radius: 16px;
    background: rgba(255,255,255,.04);
}

.benefit-number {
    color: var(--gold);
    font-weight: 900;
}

.process-section {
    background: #091526;
}

.process-grid {
    display: grid;
    grid-template-columns: repeat(3,1fr);
    gap: 16px;
    margin-top: 50px;
}

.process-card {
    padding: 35px;
    border-top: 2px solid var(--gold);
    background: rgba(255,255,255,.04);
}

.process-card > span {
    color: var(--gold);
    font-weight: 900;
}

.process-card h3 {
    margin-top: 45px;
}

.local-section {
    padding: 105px 0;
    background:
        radial-gradient(
            circle at 85% 50%,
            rgba(215,181,109,.13),
            transparent 30%
        ),
        #0b1829;
}

.location-box {
    margin-top: 25px;
    padding: 25px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: rgba(255,255,255,.04);
}

.location-box h3 {
    color: var(--text);
}

.faq {
    max-width: 900px;
    margin-top: 45px;
    display: grid;
    gap: 12px;
}

details {
    padding: 23px 26px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: rgba(255,255,255,.04);
}

summary {
    cursor: pointer;
    font-weight: 900;
}

details p {
    color: var(--muted);
}

.cta-section {
    padding: 105px 0;
}

.cta-box {
    padding: 60px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 50px;
    border: 1px solid var(--border);
    border-radius: 24px;
    background:
        radial-gradient(
            circle at 90% 20%,
            rgba(215,181,109,.2),
            transparent 35%
        ),
        linear-gradient(135deg,#13243a,#081321);
}

.cta-box p {
    max-width: 650px;
    color: var(--muted);
    font-size: 18px;
}

.cta-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
}

.footer {
    padding: 40px 0;
    border-top: 1px solid var(--border);
}

.footer-grid {
    display: flex;
    justify-content: space-between;
    gap: 30px;
}

.footer p {
    color: var(--muted);
}

:focus-visible {
    outline: 2px solid var(--gold);
    outline-offset: 4px;
}

@media (max-width: 850px) {

    nav {
        display: none;
    }

    .hero {
        min-height: 650px;
    }

    .hero-grid,
    .intro-grid,
    .about-grid,
    .local-grid,
    .service-grid,
    .benefit-grid,
    .process-grid {
        grid-template-columns: 1fr;
    }

    .hero-visual {
        min-height: 300px;
    }

    .visual-main strong {
        font-size: 55px;
    }

    .section {
        padding: 80px 0;
    }

    .cta-box {
        padding: 35px;
        flex-direction: column;
        align-items: flex-start;
    }

    .footer-grid {
        flex-direction: column;
    }
}

@media (prefers-reduced-motion: reduce) {
    html {
        scroll-behavior: auto;
    }

    *,
    *::before,
    *::after {
        animation-duration: .01ms !important;
        transition-duration: .01ms !important;
    }
}
"""


JS = r"""
document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function () {
        var target = document.querySelector(
            link.getAttribute("href")
        );

        if (target) {
            target.scrollIntoView({
                behavior: "smooth"
            });
        }
    });
});
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
        or "Local Junk Removal"
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


def generate_copy(business, handoff):
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
            "business": business,
            "ai_handoff": handoff,
        },
        ensure_ascii=False,
        indent=2,
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


def build_html(business, copy):
    name = get_business_name(business, {})

    phone = business.get("phone", "")
    address = business.get("address", "")
    website = business.get("website", "")

    headline = copy.get(
        "headline",
        f"Professional Junk Removal in Your Area",
    )

    subheadline = copy.get(
        "subheadline",
        "",
    )

    intro = copy.get(
        "intro",
        "",
    )

    about_title = copy.get(
        "about_title",
        "Local Junk Removal Made Simple",
    )

    about = copy.get(
        "about",
        "",
    )

    services_intro = copy.get(
        "services_intro",
        "",
    )

    services = copy.get(
        "services",
        [],
    )

    benefits = copy.get(
        "benefits",
        [],
    )

    process = copy.get(
        "process",
        [],
    )

    local_intro = copy.get(
        "local_intro",
        "",
    )

    faq = copy.get(
        "faq",
        [],
    )

    cta_title = copy.get(
        "cta_title",
        "Ready to Clear the Clutter?",
    )

    cta_text = copy.get(
        "cta_text",
        "",
    )

    phone_html = phone_link(phone)

    services_html = ""

    for index, service in enumerate(
        services[:8],
        1,
    ):
        if not isinstance(service, dict):
            continue

        service_name = service.get(
            "name",
            "",
        )

        description = service.get(
            "description",
            "",
        )

        if service_name and description:
            services_html += f"""
            <article class="service-card">
                <span class="service-number">
                    {index:02d}
                </span>

                <h3>
                    {escape(str(service_name))}
                </h3>

                <p>
                    {escape(str(description))}
                </p>
            </article>
            """

    if not services_html:
        services_html = """
        <article class="service-card">
            <span class="service-number">01</span>

            <h3>
                Junk Removal
            </h3>

            <p>
                Contact the business directly to discuss your junk removal needs
                and determine the appropriate service for your situation.
            </p>
        </article>
        """

    benefits_html = ""

    for index, benefit in enumerate(
        benefits[:4],
        1,
    ):
        if benefit:
            benefits_html += f"""
            <article class="benefit-card">
                <span class="benefit-number">
                    {index:02d}
                </span>

                <h3>
                    {escape(str(benefit))}
                </h3>
            </article>
            """

    process_html = ""

    for index, item in enumerate(
        process[:3],
        1,
    ):
        if not isinstance(item, dict):
            continue

        title = item.get(
            "title",
            "",
        )

        text = item.get(
            "text",
            "",
        )

        if title and text:
            process_html += f"""
            <article class="process-card">

                <span>
                    {index:02d}
                </span>

                <h3>
                    {escape(str(title))}
                </h3>

                <p>
                    {escape(str(text))}
                </p>

            </article>
            """

    faq_html = ""

    for item in faq[:5]:
        if not isinstance(item, dict):
            continue

        question = item.get(
            "question",
            "",
        )

        answer = item.get(
            "answer",
            "",
        )

        if question and answer:
            faq_html += f"""
            <details>
                <summary>
                    {escape(str(question))}
                </summary>

                <p>
                    {escape(str(answer))}
                </p>
            </details>
            """

    location_html = ""

    if address:
        location_html = f"""
        <div class="location-box">
            <span class="eyebrow">
                LOCAL LOCATION
            </span>

            <h3>
                {escape(str(address))}
            </h3>
        </div>
        """

    website_html = ""

    if website:
        website_html = f"""
        <a
            class="button secondary"
            href="{escape(str(website))}"
            target="_blank"
            rel="noopener"
        >
            Visit Website
        </a>
        """

    return f"""<!doctype html>
<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    {escape(str(name))} | Junk Removal
</title>

<meta
    name="description"
    content="{escape(str(subheadline))}"
>

<link
    rel="stylesheet"
    href="styles.css"
>

</head>


<body>


<header class="header">

    <div class="container nav">

        <a
            class="logo"
            href="#"
        >
            {escape(str(name))}
        </a>

        <nav>
            <a href="#services">Services</a>
            <a href="#about">About</a>
            <a href="#process">How It Works</a>
            <a href="#faq">FAQ</a>
            <a href="#contact">Contact</a>
        </nav>

        {phone_html}

    </div>

</header>


<main>


<section class="hero">

    <div class="hero-pattern"></div>

    <div class="container hero-grid">

        <div class="hero-content">

            <span class="eyebrow">
                LOCAL JUNK REMOVAL
            </span>

            <h1>
                {escape(str(headline))}
            </h1>

            <p class="hero-copy">
                {escape(str(subheadline))}
            </p>

            <div class="actions">

                {phone_html}

                <a
                    class="button secondary"
                    href="#contact"
                >
                    Get Started
                </a>

            </div>

            {
                f'<p class="location">{escape(str(address))}</p>'
                if address
                else ""
            }

        </div>


        <div class="hero-visual">

            <div class="visual-main">

                <span>
                    JUNK
                </span>

                <strong>
                    REMOVAL
                </strong>

            </div>

            <div class="visual-small">
                CLEAR SPACE.<br>
                MOVE FORWARD.
            </div>

        </div>

    </div>

</section>


<section class="intro-section">

    <div class="container intro-grid">

        <div>

            <span class="eyebrow">
                JUNK REMOVAL SERVICE
            </span>

            <h2>
                {escape(str(about_title))}
            </h2>

        </div>

        <div class="intro-copy">

            <p>
                {escape(str(intro))}
            </p>

        </div>

    </div>

</section>


<section
    id="services"
    class="section"
>

    <div class="container">

        <div class="section-heading">

            <span class="eyebrow">
                JUNK REMOVAL SERVICES
            </span>

            <h2>
                Clear Out What You No Longer Need
            </h2>

            <p>
                {escape(str(services_intro))}
            </p>

        </div>

        <div class="service-grid">
            {services_html}
        </div>

    </div>

</section>


<section
    id="about"
    class="section dark"
>

    <div class="container about-grid">

        <div class="about-number">
            01
        </div>

        <div>

            <span class="eyebrow">
                ABOUT
            </span>

            <h2>
                {escape(str(about_title))}
            </h2>

            <p class="large-copy">
                {escape(str(about))}
            </p>

        </div>

    </div>

</section>


<section class="section">

    <div class="container">

        <div class="section-heading">

            <span class="eyebrow">
                WHY IT MATTERS
            </span>

            <h2>
                A Cleaner Space Starts Here
            </h2>

        </div>

        <div class="benefit-grid">
            {benefits_html}
        </div>

    </div>

</section>


<section
    id="process"
    class="section process-section"
>

    <div class="container">

        <div class="section-heading">

            <span class="eyebrow">
                HOW IT WORKS
            </span>

            <h2>
                Simple Steps. Less Clutter.
            </h2>

        </div>

        <div class="process-grid">
            {process_html}
        </div>

    </div>

</section>


<section class="local-section">

    <div class="container local-grid">

        <div>

            <span class="eyebrow">
                LOCAL JUNK REMOVAL
            </span>

            <h2>
                Local Service When You Need It
            </h2>

        </div>

        <div class="local-copy">

            <p>
                {escape(str(local_intro))}
            </p>

            {location_html}

        </div>

    </div>

</section>


{
    f'''
<section
    id="faq"
    class="section faq-section"
>

    <div class="container">

        <div class="section-heading">

            <span class="eyebrow">
                FAQ
            </span>

            <h2>
                Junk Removal Questions
            </h2>

        </div>

        <div class="faq">
            {faq_html}
        </div>

    </div>

</section>
'''
    if faq_html
    else ""
}


<section
    id="contact"
    class="cta-section"
>

    <div class="container cta-box">

        <div>

            <span class="eyebrow">
                GET STARTED
            </span>

            <h2>
                {escape(str(cta_title))}
            </h2>

            <p>
                {escape(str(cta_text))}
            </p>

        </div>

        <div class="cta-actions">

            {phone_html}

            {website_html}

        </div>

    </div>

</section>


</main>


<footer class="footer">

    <div class="container footer-grid">

        <div>

            <strong>
                {escape(str(name))}
            </strong>

            {
                f'<p>{escape(str(address))}</p>'
                if address
                else ""
            }

        </div>

        <div>
            {phone_html}
        </div>

    </div>

</footer>


<script src="script.js"></script>

</body>

</html>
"""


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

    copy = generate_copy(
        business,
        handoff,
    )

    html = build_html(
        business,
        copy,
    )

    output_dir = (
        handoff_path.parent / "website"
    )

    output_dir.mkdir(
        exist_ok=True
    )

    (output_dir / "index.html").write_text(
        html,
        encoding="utf-8",
    )

    (output_dir / "styles.css").write_text(
        CSS,
        encoding="utf-8",
    )

    (output_dir / "script.js").write_text(
        JS,
        encoding="utf-8",
    )

    (output_dir / "ELEMENTOR_REBUILD_NOTES.md").write_text(
        """# Elementor Rebuild Notes

Recreate the generated page using Elementor Pro.

Recommended structure:

1. Header
2. Hero
3. Intro
4. Services
5. About
6. Benefits
7. How It Works
8. Local Section
9. FAQ
10. CTA
11. Footer

Recommended widgets:

- Containers
- Heading
- Text Editor
- Button
- Icon
- Icon Box
- Accordion
- Form
- Google Maps when appropriate

Do not add unsupported business claims.
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

    parser.add_argument(
        "ai_handoff",
        help="Path to AI_HANDOFF.json",
    )

    args = parser.parse_args()

    result = generate_website(
        args.ai_handoff
    )

    print(
        f"\nWebsite created: {result}"
    )