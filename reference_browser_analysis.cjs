// Optional rendered evidence. Install Playwright and Chromium, or set NODE_PATH
// to an existing Playwright installation. No source copy, logos or assets exported.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const [url, output, mode = 'reference'] = process.argv.slice(2);
  if (!url || !output) throw new Error('Usage: node reference_browser_analysis.cjs URL OUTPUT [reference|qa]');
  let browser;
  for (const channel of [undefined, 'chrome', 'msedge']) {
    try { browser = await chromium.launch({ headless: true, channel }); break; }
    catch (error) { if (channel === 'msedge') throw error; }
  }
  const results = [];
  const errors = [];
  try {
    const page = await browser.newPage();
    page.on('pageerror', error => errors.push(error.message.slice(0, 200)));
    for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 834, 1112], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      if (response && !response.ok()) throw new Error(`Reference returned HTTP ${response.status()}`);
      await page.evaluate(() => document.fonts.ready);
      // Reset sites that preserve/restore scroll, and let responsive layout settle.
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(900);
      const evidence = await page.evaluate(() => {
        const visible = el => el && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0 && getComputedStyle(el).visibility !== 'hidden';
        const inViewport = el => {
          if (!visible(el)) return false;
          const r = el.getBoundingClientRect();
          return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
        };
        const sample = el => {
          if (!el || !visible(el)) return null;
          const s = getComputedStyle(el), b = el.getBoundingClientRect();
          return {
            tag: el.tagName.toLowerCase(), x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height),
            display: s.display, position: s.position, columns: s.gridTemplateColumns, gap: s.gap,
            padding: s.padding, margin: s.margin, background: s.backgroundColor, color: s.color,
            font_family: s.fontFamily, font_size: s.fontSize, font_weight: s.fontWeight, line_height: s.lineHeight,
            text_transform: s.textTransform, text_align: s.textAlign, letter_spacing: s.letterSpacing,
            radius: s.borderRadius, border: s.borderTop, object_fit: s.objectFit,
            animation: s.animationName, transition: s.transition, transform: s.transform,
          };
        };
        const main = document.querySelector('main,[role="main"]');
        const h1s = [...document.querySelectorAll('h1')];
        const visibleHeading = h1s.find(inViewport);
        const primaryHeading = visibleHeading || h1s.find(el => main?.contains(el)) || h1s[0];
        const headerCandidates = [...document.querySelectorAll('header,[role="banner"]')].filter(visible);
        const header = headerCandidates.find(el => el.querySelector('nav,[role="navigation"]')) || headerCandidates[0];
        const candidateSet = new Set([
          ...document.querySelectorAll('.hero,[class~="hero"],[class*="hero"],main > section,main > article,main > div,body > section'),
        ]);
        for (let node = primaryHeading?.parentElement; node && node !== main && node !== document.body; node = node.parentElement) {
          candidateSet.add(node);
        }
        const heroCandidates = [...candidateSet].filter(el => {
          if (!inViewport(el)) return false;
          const r = el.getBoundingClientRect();
          return r.width >= innerWidth * 0.68 && r.height >= Math.max(180, innerHeight * 0.24)
            && r.top < innerHeight * 0.7 && r.bottom > 0;
        });
        const hero = heroCandidates.sort((a, b) => {
          const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
          const explicitA = /(^|\s)hero(\s|$)/i.test(a.className?.baseVal || a.className || '') ? -innerWidth : 0;
          const explicitB = /(^|\s)hero(\s|$)/i.test(b.className?.baseVal || b.className || '') ? -innerWidth : 0;
          const semanticA = a.tagName === 'SECTION' ? -innerWidth * 0.25 : 0;
          const semanticB = b.tagName === 'SECTION' ? -innerWidth * 0.25 : 0;
          return (ar.height + Math.abs(ar.top) * 0.35 + explicitA + semanticA) - (br.height + Math.abs(br.top) * 0.35 + explicitB + semanticB);
        })[0] || (primaryHeading && inViewport(primaryHeading) ? primaryHeading.parentElement : null);
        const heading = hero?.querySelector('h1') || visibleHeading || primaryHeading;
        const sections = [...document.querySelectorAll('main > section,main > div,body > section')].filter(visible).slice(0, 12);
        const media = [...(hero || document).querySelectorAll('img,video,[role="img"]')].filter(inViewport);
        const nav = header?.querySelector('nav,[role="navigation"]');
        const controls = [...(header || document).querySelectorAll('button,[role="button"],summary')].filter(visible);
        const heroButtons = hero ? [...hero.querySelectorAll('a,button,[role="button"]')].filter(inViewport) : [];
        const ctaWords = /call|contact|quote|book|schedule|consult|start|discover|explore/i;
        const heroCta = heroButtons.find(el => el.matches('a[href^="tel:"],a[href^="mailto:"]'))
          || heroButtons.find(el => ctaWords.test(`${el.innerText || ''} ${el.getAttribute('aria-label') || ''}`))
          || heroButtons.find(el => /button|btn|cta/i.test(el.className?.baseVal || el.className || ''))
          || heroButtons[0];
        const buttons = [...document.querySelectorAll('button,a[class*="button"],a[class*="btn"],.button')].filter(visible);
        return {
          viewport: { width: innerWidth, height: innerHeight }, page_url: location.href,
          body: sample(document.body), header: sample(header), navigation: sample(nav),
          nav_links_visible: [...(nav || document.createElement('div')).querySelectorAll('a')].filter(visible).length,
          mobile_controls_visible: controls.length,
          hero_selection: hero ? { tag: hero.tagName.toLowerCase(), class_name: String(hero.className?.baseVal || hero.className || '').slice(0, 160), method: 'visible h1 ancestor and top viewport geometry' } : null,
          hero: sample(hero), headline: sample(heading), hero_media: media.slice(0, 3).map(sample), hero_cta: sample(heroCta),
          headings: [...document.querySelectorAll('h2,h3')].filter(visible).slice(0, 8).map(sample),
          sections: sections.map(sample), buttons: buttons.slice(0, 4).map(sample),
          cards: [...document.querySelectorAll('article,[class*="card"]')].filter(visible).slice(0, 6).map(sample),
          footer: sample(document.querySelector('footer')), forms: document.querySelectorAll('form').length,
          faq: document.querySelectorAll('details,[class*="faq"]').length,
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          broken_images: [...document.images].filter(el => visible(el) && el.complete && !el.naturalWidth).length,
          sections_order: [...document.querySelectorAll('main > section')].map(el => el.id),
          phone_cta_visible: [...document.querySelectorAll('a[href^="tel:"]')].some(el => visible(el) && el.getBoundingClientRect().top < innerHeight),
          meta_description: !!document.querySelector('meta[name="description"]'),
          h1_count: document.querySelectorAll('h1').length,
        };
      });
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight / 2));
      await page.waitForTimeout(300);
      evidence.header_after_scroll = await page.evaluate(() => {
        const el = document.querySelector('header,[role="banner"]');
        return el ? { top: Math.round(el.getBoundingClientRect().top), position: getComputedStyle(el).position } : null;
      });
      await page.evaluate(() => window.scrollTo(0, 0));
      if (mode === 'qa' && name === 'mobile') {
        const menu = page.locator('.mobile-nav summary');
        if (await menu.isVisible()) {
          await menu.click();
          evidence.mobile_menu_opens = await page.locator('.mobile-nav nav a[href="#contact"]').isVisible();
          evidence.mobile_menu_overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
          await menu.click();
        }
      }
      const screenshot = path.join(path.dirname(output), `${mode}-${name}.png`);
      const topScreenshot = path.join(path.dirname(output), `${mode}-${name}-top.png`);
      await page.screenshot({ path: topScreenshot });
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({ name, ...evidence, screenshot: path.basename(screenshot), top_screenshot: path.basename(topScreenshot) });
    }
    // Record actual motion with reduced-motion disabled; do not infer it from a screenshot.
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.reload({ waitUntil: 'domcontentloaded' });
    if (mode === 'qa') {
      await page.locator('.scroll-reveal').first().scrollIntoViewIfNeeded();
    }
    await page.waitForTimeout(150);
    const motion = await page.evaluate(() => ({
      animations: [...new Set(document.getAnimations().map(a => a.animationName || 'web-animation'))].slice(0, 12),
      transitions: [...new Set([...document.querySelectorAll('a,button,img')].slice(0, 40).map(el => getComputedStyle(el).transition).filter(value => !value.includes('0s')))].slice(0, 8),
    }));
    if (mode === 'qa') {
      await page.locator('.hero .button').hover();
      await page.waitForTimeout(1100);
      motion.button_hover_transform = await page.locator('.hero .button').evaluate(el => getComputedStyle(el).transform);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.reload({ waitUntil: 'domcontentloaded' });
      motion.reduced_motion_animations = await page.evaluate(() => document.getAnimations().length);
    }
    fs.writeFileSync(output, JSON.stringify({ viewports: results, motion, page_errors: errors, limitations: ['Scroll choreography and hover intent require manual review; samples represent visible DOM, not the entire design system.'] }, null, 2) + '\n');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
