"""Rendered reference measurements, kept outside generated website assets."""
from pathlib import Path
import hashlib
import re


MEASURE_DESIGN = """() => {
    const rect = el => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)}; };
    const visible = el => {
        const r=el.getBoundingClientRect();
        if(r.width<=10||r.height<=10||r.right<=0||r.left>=innerWidth||el.closest('[role="dialog"],[aria-modal="true"],[id*="cookie"],[class*="cookie"],[id*="consent"]')) return false;
        for(let p=el;p;p=p.parentElement){const s=getComputedStyle(p);if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)<.05||p.getAttribute('aria-hidden')==='true')return false;}
        return true;
    };
    const describe = el => { const s=getComputedStyle(el); return {tag:el.tagName,text:el.innerText?.slice(0,100),rect:rect(el),font:s.fontFamily,size:s.fontSize,weight:s.fontWeight,lineHeight:s.lineHeight,color:s.color,background:s.backgroundColor,radius:s.borderRadius,display:s.display,padding:s.padding}; };
    const headings=[...document.querySelectorAll('h1,h2')].filter(visible).slice(0,8).map(describe);
    const images=[...document.images].filter(el=>visible(el)&&!el.closest('header,nav,[role="navigation"]')).slice(0,12).map(el=>({rect:rect(el),fit:getComputedStyle(el).objectFit,alt:el.alt}));
    let sectionElements=[...document.querySelectorAll('main>section,main>div,body>section')].filter(visible);
    if(!sectionElements.length){
        const candidates=[...document.querySelectorAll('article,[role="main"]>div,[data-section],body>div')];
        sectionElements=candidates.filter(el=>visible(el)&&el.getBoundingClientRect().width>innerWidth*.45&&el.getBoundingClientRect().height>120&&
            [...el.querySelectorAll('h1,h2,p,img,span,a')].some(child=>visible(child)&&!child.closest('header,nav,[role="navigation"]')&&(child.tagName==='IMG'||child.textContent.trim().length>35)));
    }
    const sections=sectionElements.slice(0,10).map(el=>({
        ...describe(el),
        section_layouts:{
            children:[...el.children].filter(visible).slice(0,8).map(describe),
            headings:[...el.querySelectorAll('h1,h2,h3')].filter(visible).slice(0,6).map(describe),
            images:[...el.querySelectorAll('img')].filter(visible).slice(0,6).map(image=>({rect:rect(image),fit:getComputedStyle(image).objectFit})),
            grids:[...el.querySelectorAll('*')].filter(child=>visible(child)&&getComputedStyle(child).display==='grid').slice(0,4).map(child=>({rect:rect(child),columns:getComputedStyle(child).gridTemplateColumns,gap:getComputedStyle(child).gap})),
            text_alignment:getComputedStyle(el).textAlign
        }
    }));
    const controls=[...document.querySelectorAll('button,a[class*="button"],a[class*="btn"]')].filter(visible).slice(0,5).map(describe);
    const htmlBackground=getComputedStyle(document.documentElement).backgroundColor;
    const canvas_background=htmlBackground==='rgba(0, 0, 0, 0)'?'rgb(255, 255, 255)':htmlBackground;
    return {viewport:{width:innerWidth,height:innerHeight},canvas_background,body:describe(document.body),headings,images,sections,controls};
}"""


def inspect_rendered_reference(url, output_dir=None):
    """Measure a real desktop render; gracefully report unavailable browsers."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        browser = None
        for channel in (None, "msedge", "chrome"):
            try:
                browser = runtime.chromium.launch(headless=True, timeout=10000, **({"channel": channel} if channel else {}))
                break
            except Exception:
                continue
        if browser is None:
            return {"status": "unavailable", "note": "Install Chromium with: python -m playwright install chromium"}
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            # Give layout a chance to settle without depending on analytics being idle.
            try:
                page.wait_for_load_state("load", timeout=8000)
            except Exception:
                pass
            # An isolated research browser can decline optional cookies.
            try:
                decline = page.get_by_role("button", name=re.compile(r"reject all|reject optional|only necessary|only essential|decline", re.I)).first
                if decline.is_visible(timeout=1000):
                    decline.click(timeout=1500)
            except Exception:
                pass
            # Resolve a locale selector without purchasing or accepting marketing.
            # Otherwise its geometry and colors can contaminate source measurements.
            for role in ("button", "link"):
                try:
                    international = page.get_by_role(role, name=re.compile(r"^International\s*\(EUR\)$", re.I)).first
                    if international.is_visible(timeout=500):
                        international.click(timeout=2000)
                        page.wait_for_timeout(400)
                        break
                except Exception:
                    pass
            page.evaluate("() => Promise.race([document.fonts.ready, new Promise(resolve => setTimeout(resolve, 2000))])")
            observations = page.evaluate(MEASURE_DESIGN)
            if not observations.get("sections"):
                # Trigger lazy/scroll-reveal content before declaring a render empty.
                page.evaluate("() => {scrollTo(0,Math.min(500,document.body.scrollHeight));}")
                page.wait_for_timeout(600)
                page.evaluate("scrollTo(0,0)")
                observations = page.evaluate(MEASURE_DESIGN)
            if output_dir:
                folder = Path(output_dir)
                folder.mkdir(parents=True, exist_ok=True)
                filename = hashlib.sha256(url.encode()).hexdigest()[:12] + ".png"
                page.screenshot(path=str(folder / filename), animations="disabled", timeout=15000)
                observations["screenshot"] = filename
            status = "measured" if observations.get("sections") else "unavailable"
            return {"status": status, "basis": "Rendered desktop computed styles and element geometry; mobile and motion not inspected.",
                    **({"note": "No usable content sections were visible; this source cannot ground a composition."} if status != "measured" else {}), **observations}
        finally:
            browser.close()
