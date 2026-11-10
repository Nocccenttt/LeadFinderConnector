/* Rare marketing introductions, with immediate keyboard and reduced-motion states. */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const active = new Set();
  let keyboard = false;
  const finish = () => { for (const animation of active) animation.cancel(); active.clear(); };
  addEventListener('keydown', () => { keyboard = true; document.body.dataset.input = 'keyboard'; finish(); }, true);
  addEventListener('pointerdown', () => { keyboard = false; document.body.dataset.input = 'pointer'; }, {capture:true, passive:true});
  addEventListener('focusin', finish);
  reduce.addEventListener('change', () => { if (reduce.matches) finish(); });
  function introduce(el, delay = 0) {
    if (reduce.matches || keyboard || !el.animate) return;
    const animation = el.animate([{opacity:0, transform:'translateY(14px)'}, {opacity:1, transform:'translateY(0)'}],
      {duration:560, delay, easing:'cubic-bezier(0.23, 1, 0.32, 1)', fill:'both'});
    active.add(animation);
    animation.onfinish = () => { active.delete(animation); animation.cancel(); };
    animation.oncancel = () => active.delete(animation);
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach((entry, index) => { if (entry.isIntersecting) { introduce(entry.target, (index % 4) * 60); observer.unobserve(entry.target); } });
    }, {threshold:.12, rootMargin:'0px 0px -24px 0px'});
    document.querySelectorAll('.rc-title,.rc-text,.rc-image,.rc-items').forEach(el => observer.observe(el));
  }
  const toggle = document.querySelector('.menu-toggle'), nav = document.querySelector('.site-nav');
  const close = () => { if (toggle && nav) { toggle.setAttribute('aria-expanded','false'); nav.classList.remove('is-open'); } };
  addEventListener('keydown', e => { if (e.key === 'Escape' && toggle?.getAttribute('aria-expanded') === 'true') { close(); toggle.focus(); } });
  addEventListener('pointerdown', e => { if (toggle && nav && !toggle.contains(e.target) && !nav.contains(e.target)) close(); });
})();
