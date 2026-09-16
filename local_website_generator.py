import argparse
import html
import json
from pathlib import Path


def load_handoff(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def generate_website(handoff_path):
    handoff_path = Path(handoff_path)
    handoff = load_handoff(handoff_path)

    business = handoff["business"]
    lead = handoff["lead"]
    online = handoff["verified_online_presence"]

    name = html.escape(business.get("name", "Local Business"))
    address = html.escape(business.get("address", ""))
    phone = html.escape(business.get("phone", ""))
    website = html.escape(business.get("website", ""))
    status = html.escape(business.get("website_status", ""))
    opportunity = html.escape(lead.get("opportunity", ""))
    reason = html.escape(lead.get("reason", ""))

    phone_link = "".join(
        character for character in phone
        if character.isdigit() or character == "+"
    )

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name}</title>
    <meta name="description"
          content="{name} - local business website.">
    <link rel="stylesheet" href="styles.css">
</head>

<body>

<header class="site-header">
    <div class="container nav">
        <a class="logo" href="#">{name}</a>

        <a class="phone-button" href="tel:{phone_link}">
            Call Now
        </a>
    </div>
</header>

<main>

<section class="hero">
    <div class="container hero-content">

        <p class="eyebrow">LOCAL BUSINESS</p>

        <h1>{name}</h1>

        <p class="hero-text">
            A professional local business website built around
            verified business information.
        </p>

        <div class="actions">
            <a class="button primary" href="tel:{phone_link}">
                Call {name}
            </a>

            <a class="button secondary" href="#contact">
                Contact Us
            </a>
        </div>

    </div>
</section>


<section class="section">
    <div class="container">

        <p class="eyebrow">ABOUT</p>

        <h2>Professional Local Service</h2>

        <p>
            {name} is located at {address}.
            Contact the business directly at {phone}.
        </p>

    </div>
</section>


<section class="section contact-section" id="contact">
    <div class="container">

        <p class="eyebrow">CONTACT</p>

        <h2>Get In Touch</h2>

        <div class="contact-card">

            <div>
                <strong>Phone</strong>
                <a href="tel:{phone_link}">{phone}</a>
            </div>

            <div>
                <strong>Address</strong>
                <span>{address}</span>
            </div>

        </div>

    </div>
</section>


<section class="section opportunity">
    <div class="container">

        <p class="eyebrow">WEBSITE OPPORTUNITY</p>

        <h2>LeadFinder Test Data</h2>

        <p>
            Opportunity: {opportunity}
        </p>

        <p>
            {reason}
        </p>

        <p class="test-note">
            This section is included for local testing and should
            not be included in the final customer website.
        </p>

    </div>
</section>

</main>


<footer class="site-footer">
    <div class="container">
        <p>{name}</p>
        <p>{address}</p>
        <p>{phone}</p>
    </div>
</footer>

<script src="script.js"></script>

</body>
</html>
"""

    styles_css = """
* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;
    color: #172033;
    background: #ffffff;
    line-height: 1.6;
}

.container {
    width: min(1100px, 92%);
    margin: 0 auto;
}

.site-header {
    border-bottom: 1px solid #e8ebf0;
    background: #ffffff;
}

.nav {
    min-height: 72px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
}

.logo {
    color: #172033;
    font-size: 20px;
    font-weight: 700;
    text-decoration: none;
}

.phone-button,
.button {
    display: inline-block;
    padding: 13px 20px;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 700;
}

.phone-button,
.primary {
    color: #ffffff;
    background: #172033;
}

.secondary {
    color: #172033;
    border: 1px solid #172033;
}

.hero {
    padding: 110px 0;
    background: #f4f6f8;
}

.hero-content {
    max-width: 800px;
}

.eyebrow {
    margin-bottom: 12px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
}

h1 {
    margin: 0 0 20px;
    font-size: clamp(42px, 8vw, 76px);
    line-height: 1.05;
}

h2 {
    margin-top: 0;
    font-size: clamp(30px, 5vw, 48px);
    line-height: 1.15;
}

.hero-text {
    max-width: 650px;
    margin-bottom: 30px;
    font-size: 20px;
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
}

.section {
    padding: 90px 0;
}

.contact-section {
    background: #f4f6f8;
}

.contact-card {
    display: grid;
    gap: 20px;
    padding: 30px;
    border-radius: 12px;
    background: #ffffff;
}

.contact-card div {
    display: grid;
    gap: 5px;
}

.contact-card a {
    color: #172033;
    font-weight: 700;
}

.opportunity {
    background: #fff8e8;
}

.test-note {
    margin-top: 30px;
    font-size: 13px;
    opacity: 0.7;
}

.site-footer {
    padding: 40px 0;
    color: #ffffff;
    background: #172033;
}

.site-footer p {
    margin: 5px 0;
}

@media (max-width: 600px) {
    .hero {
        padding: 75px 0;
    }

    .section {
        padding: 65px 0;
    }

    .phone-button {
        padding: 10px 14px;
    }
}
"""

    script_js = """
document.addEventListener("DOMContentLoaded", () => {
    console.log("LeadFinder local website test loaded.");
});
"""

    output_dir = handoff_path.parent / "website"
    output_dir.mkdir(exist_ok=True)

    files = {
        "index.html": index_html,
        "styles.css": styles_css,
        "script.js": script_js,
    }

    for filename, content in files.items():
        (output_dir / filename).write_text(
            content,
            encoding="utf-8",
        )

    return output_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a local test website from an AI handoff."
    )

    parser.add_argument(
        "ai_handoff",
        help="Path to AI_HANDOFF.json",
    )

    args = parser.parse_args()

    output = generate_website(args.ai_handoff)

    print(f"Website created: {output}")