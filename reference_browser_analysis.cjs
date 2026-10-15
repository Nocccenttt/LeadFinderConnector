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
      // Let lazy loaded layout settle, then sample at the top and after scrolling.
      await page.waitForTimeout(1200);
      const evidence = await page.evaluate(() => {
        const visible = el => el && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0 && getComputedStyle(el).visibility !== 'hidden';
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
        const heading = document.querySelector('h1');
        const header = document.querySelector('header,[role="banner"]');
        const hero = document.querySelector('.hero,[class*="hero"],main > section,main > div') || heading?.parentElement;
        const sections = [...document.querySelectorAll('main > section,main > div,body > section')].filter(visible).slice(0, 12);
        const media = [...(hero || document).querySelectorAll('img,video')].filter(visible);
        const nav = header?.querySelector('nav,[role="navigation"]');
        const controls = [...(header || document).querySelectorAll('button,[role="button"],summary')].filter(visible);
        const buttons = [...document.querySelectorAll('button,a[class*="button"],a[class*="btn"],.button')].filter(visible);
        return {
          viewport: { width: innerWidth, height: innerHeight }, page_url: location.href,
          body: sample(document.body), header: sample(header), navigation: sample(nav),
          nav_links_visible: [...(nav || document.createElement('div')).querySelectorAll('a')].filter(visible).length,
          mobile_controls_visible: controls.length,
          hero: sample(hero), headline: sample(heading), hero_media: media.slice(0, 3).map(sample), hero_cta: sample(buttons[0]),
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
      await page.screenshot({ path: screenshot, fullPage: true });
      results.push({ name, ...evidence, screenshot: path.basename(screenshot) });
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
