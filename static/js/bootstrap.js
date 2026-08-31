(() => {
  const assetVersion = document.currentScript?.dataset.assetVersion || "";
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const desktop = window.matchMedia("(min-width: 1024px)");
  const progressFill = document.querySelector("[data-scroll-progress]");
  const stickyReserve = document.querySelector("[data-sticky-reserve]");
  const reservationWidget = document.querySelector("[data-reservation-widget]");
  const richMotionRoot = document.querySelector("#story");
  const idle = window.requestIdleCallback
    ? (callback, timeout = 1200) => window.requestIdleCallback(callback, { timeout })
    : (callback, timeout = 1200) => window.setTimeout(callback, Math.min(timeout, 400));

  const loadScript = (src) => new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const separator = src.includes("?") ? "&" : "?";
    script.src = assetVersion
      ? `${src}${separator}v=${encodeURIComponent(assetVersion)}`
      : src;
    script.async = true;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", reject, { once: true });
    document.head.append(script);
  });

  const updateProgress = () => {
    if (!progressFill) return;
    const range = document.documentElement.scrollHeight - window.innerHeight;
    const progress = range > 0 ? Math.min(1, Math.max(0, window.scrollY / range)) : 1;
    progressFill.style.transform = `scaleY(${progress})`;
  };

  const initializeLightMotion = () => {
    if (reducedMotion.matches) {
      stickyReserve?.classList.add("is-active");
      if (progressFill) progressFill.style.transform = "scaleY(1)";
      return;
    }

    const sections = [
      ".story-section > .site-shell",
      ".menu-transition-grid",
      ".philosophy-content",
      ".reservation-transition-content"
    ].map((selector) => document.querySelector(selector)).filter(Boolean);

    sections.forEach((section) => section.classList.add("lite-reveal"));
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -10%", threshold: 0.08 });
    sections.forEach((section) => revealObserver.observe(section));

    let ticking = false;
    const requestProgressUpdate = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        updateProgress();
        ticking = false;
      });
    };
    updateProgress();
    window.addEventListener("scroll", requestProgressUpdate, { passive: true });
    window.addEventListener("resize", requestProgressUpdate, { passive: true });

    const reserveSection = document.querySelector("#reserve");
    if (reserveSection && stickyReserve) {
      const reserveObserver = new IntersectionObserver((entries, observer) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        stickyReserve.classList.add("is-active");
        observer.disconnect();
      }, { rootMargin: "0px 0px -20%", threshold: 0.05 });
      reserveObserver.observe(reserveSection);
    }
  };

  const loadDesktopMotion = async () => {
    try {
      await loadScript("/static/js/vendor/gsap.min.js");
      await loadScript("/static/js/vendor/ScrollTrigger.min.js");
      await loadScript("/static/js/vendor/lenis.min.js");
      await loadScript("/static/js/motion.js");
    } catch (_error) {
      initializeLightMotion();
    }
  };

  const loadReservations = () => loadScript("/static/js/reservations.js").catch(() => {});

  if (richMotionRoot && desktop.matches && !reducedMotion.matches) {
    window.addEventListener("load", () => idle(loadDesktopMotion, 800), { once: true });
  } else {
    initializeLightMotion();
  }

  if (reservationWidget) {
    let reservationLoaded = false;
    const ensureReservations = () => {
      if (reservationLoaded) return;
      reservationLoaded = true;
      loadReservations();
    };
    const reservationObserver = new IntersectionObserver((entries, observer) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      ensureReservations();
      observer.disconnect();
    }, { rootMargin: "800px 0px", threshold: 0 });
    reservationObserver.observe(reservationWidget);
    window.addEventListener("load", () => idle(ensureReservations, 2200), { once: true });
  }
})();
