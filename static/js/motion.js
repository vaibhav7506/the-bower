(() => {
  if (!window.gsap || !window.ScrollTrigger) return;

  const { gsap, ScrollTrigger } = window;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const desktop = window.matchMedia("(min-width: 1024px)");

  gsap.registerPlugin(ScrollTrigger);

  const progressFill = document.querySelector("[data-scroll-progress]");
  const stickyReserve = document.querySelector("[data-sticky-reserve]");
  const storyLine = document.querySelector("[data-story-line]");
  const storyCurtain = document.querySelector("[data-story-curtain]");
  const storyContent = document.querySelector(".story-section > .site-shell");
  const momentFrames = gsap.utils.toArray(".moment-frame");
  const menuIntro = document.querySelector("[data-menu-intro]");
  const philosophyPanel = document.querySelector("[data-philosophy-panel]");
  const philosophyContent = document.querySelector("[data-philosophy-content]");
  const reservationCover = document.querySelector("[data-reservation-cover]");
  const reservationContent = document.querySelector("[data-reservation-content]");

  if (reducedMotion.matches) {
    gsap.set([storyLine, storyCurtain], { clearProps: "transform" });
    gsap.set([storyContent, ...momentFrames, menuIntro, philosophyContent, reservationContent], {
      clearProps: "all"
    });
    gsap.set(philosophyPanel, { xPercent: 0 });
    gsap.set(reservationCover, { xPercent: 101 });
    gsap.set(stickyReserve, { yPercent: 0, opacity: 1 });
    gsap.set(progressFill, { scaleY: 1 });
    stickyReserve?.classList.add("is-active");
    return;
  }

  if (progressFill) {
    gsap.to(progressFill, {
      scaleY: 1,
      ease: "none",
      scrollTrigger: {
        trigger: document.documentElement,
        start: "top top",
        end: "bottom bottom",
        scrub: 0.2
      }
    });
  }

  let lenis;
  if (window.Lenis && desktop.matches) {
    lenis = new window.Lenis({
      duration: 1.15,
      smoothWheel: true,
      wheelMultiplier: 0.88,
      touchMultiplier: 1
    });

    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((time) => lenis.raf(time * 1000));
    gsap.ticker.lagSmoothing(0);

    document.querySelectorAll('a[href^="#"]').forEach((link) => {
      link.addEventListener("click", (event) => {
        const target = document.querySelector(link.getAttribute("href"));
        if (!target) return;
        event.preventDefault();
        lenis.scrollTo(target, { offset: -24, duration: 1.2 });
      });
    });
  }

  const media = gsap.matchMedia();

  media.add("(min-width: 1024px)", () => {
    gsap.set(storyCurtain, { scaleY: 1, transformOrigin: "top center" });
    gsap.set(storyContent, { y: 72 });

    gsap.timeline({
      defaults: { ease: "power3.inOut" },
      scrollTrigger: {
        trigger: "#story",
        start: "top 82%",
        toggleActions: "play none none reverse"
      }
    })
      .to(storyLine, { scaleX: 1, duration: 1 })
      .to(storyCurtain, { scaleY: 0, duration: 1.45 }, 0.72)
      .to(storyContent, { y: 0, duration: 1.15 }, 0.9);

    gsap.set(menuIntro, { y: 42 });

    gsap.timeline({
      defaults: { ease: "power3.out" },
      scrollTrigger: {
        trigger: "#menu",
        start: "top 78%",
        toggleActions: "play none none reverse"
      }
    })
      .to(momentFrames, {
        y: -54,
        opacity: 0,
        duration: 1.15,
        stagger: 0.14
      })
      .to(menuIntro, { y: 0, duration: 0.95 }, 0.58);

    gsap.set(philosophyContent, { y: 48, opacity: 0 });

    gsap.timeline({
      defaults: { ease: "power3.inOut" },
      scrollTrigger: {
        trigger: "#philosophy",
        start: "top 76%",
        toggleActions: "play none none reverse"
      }
    })
      .fromTo(philosophyPanel, { xPercent: -101 }, { xPercent: 0, duration: 1.65 })
      .to(philosophyContent, { y: 0, opacity: 1, duration: 0.95, ease: "power3.out" }, 1.15);

    gsap.set(reservationContent, { y: 42, opacity: 0 });

    gsap.timeline({
      defaults: { ease: "power3.inOut" },
      scrollTrigger: {
        trigger: "#reserve",
        start: "top 76%",
        toggleActions: "play none none reverse"
      }
    })
      .to(reservationCover, { xPercent: 101, duration: 1.65 })
      .to(reservationContent, { y: 0, opacity: 1, duration: 0.95, ease: "power3.out" }, 0.95)
      .to(stickyReserve, {
        yPercent: 0,
        opacity: 1,
        duration: 0.6,
        onStart: () => stickyReserve?.classList.add("is-active"),
        onReverseComplete: () => stickyReserve?.classList.remove("is-active")
      }, 1.45);
  });

  media.add("(max-width: 1023px)", () => {
    const mobileSections = gsap.utils.toArray(
      ".story-section > .site-shell, .menu-transition-grid, .philosophy-content, .reservation-transition-content"
    );

    mobileSections.forEach((section) => {
      gsap.from(section, {
        y: 28,
        opacity: 0,
        duration: 0.7,
        ease: "power2.out",
        scrollTrigger: { trigger: section, start: "top 88%", once: true }
      });
    });

    gsap.set(philosophyPanel, { xPercent: 0 });
    gsap.set(reservationCover, { xPercent: 101 });

    ScrollTrigger.create({
      trigger: "#reserve",
      start: "top 80%",
      onEnter: () => {
        stickyReserve?.classList.add("is-active");
        gsap.to(stickyReserve, { yPercent: 0, opacity: 1, duration: 0.45 });
      }
    });
  });

  if (document.readyState === "complete") {
    window.requestAnimationFrame(() => ScrollTrigger.refresh());
  } else {
    window.addEventListener("load", () => ScrollTrigger.refresh(), { once: true });
  }
})();
