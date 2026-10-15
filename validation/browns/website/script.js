
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

if (!reduceMotion && document.body.dataset.reveal !== "none" && "IntersectionObserver" in window) {
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

}
if (!reduceMotion && document.body.dataset.parallax === "true" && document.body.dataset.hero === "full-bleed") {
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
