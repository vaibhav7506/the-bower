(() => {
  const preloader = document.querySelector("[data-preloader]");
  if (!preloader) return;

  const SESSION_KEY = "bower_loader_seen";
  const MIN_DISPLAY_MS = 1200;
  const MAX_DISPLAY_MS = 3500;
  const COMPLETE_HOLD_MS = 250;
  const REVEAL_MS = 720;
  const SETTLE_BUDGET_MS = 280;
  const FORCE_FINALIZE_MS = MAX_DISPLAY_MS - COMPLETE_HOLD_MS - REVEAL_MS - SETTLE_BUDGET_MS;
  const weights = { fonts: 0.3, heroImage: 0.5, domReady: 0.2 };
  const progress = { fonts: 0, heroImage: 0, domReady: 0 };
  const copy = preloader.querySelector("[data-loader-copy]");
  const paths = [...preloader.querySelectorAll(".logo-stroke")];
  const announcement = document.querySelector("[data-loader-announcement]");
  const skipLink = document.querySelector(".skip-link");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const inertTargets = [...document.querySelectorAll(".skip-link, header, main, footer, [data-sticky-reserve]")];
  const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  let hasSeenLoader = false;
  try {
    hasSeenLoader = sessionStorage.getItem(SESSION_KEY) === "seen";
  } catch (_error) {
    hasSeenLoader = false;
  }

  if (hasSeenLoader) {
    preloader.classList.add("is-hidden");
    return;
  }

  try {
    sessionStorage.setItem(SESSION_KEY, "seen");
  } catch (_error) {
    // Privacy modes can disable storage; the first-visit sequence still works.
  }

  document.documentElement.classList.add("is-loading");
  inertTargets.forEach((element) => { element.inert = true; });

  let targetProgress = 0;
  let displayedProgress = 0;
  let finalizing = false;
  let frameId;
  let settleResolver;
  let currentPhrase = "";

  const phraseFor = (value) => {
    if (value < 0.33) return "An invitation for the evening.";
    if (value < 0.66) return "The seal is set.";
    return "The room awaits.";
  };

  const paint = () => {
    const dashOffset = String(Math.max(0, 1 - displayedProgress));
    paths.forEach((path) => { path.style.strokeDashoffset = dashOffset; });

    const nextPhrase = phraseFor(displayedProgress);
    if (nextPhrase !== currentPhrase) {
      currentPhrase = nextPhrase;
      copy.textContent = nextPhrase;
    }
  };

  const tick = () => {
    const smoothing = finalizing ? 0.18 : 0.08;
    displayedProgress += (targetProgress - displayedProgress) * smoothing;

    if (Math.abs(targetProgress - displayedProgress) < 0.001) {
      displayedProgress = targetProgress;
    }

    paint();
    if (settleResolver && displayedProgress >= 0.995) {
      settleResolver();
      settleResolver = null;
    }
    frameId = window.requestAnimationFrame(tick);
  };

  const updateProgress = () => {
    targetProgress = progress.fonts * weights.fonts
      + progress.heroImage * weights.heroImage
      + progress.domReady * weights.domReady;
  };

  const markComplete = (key) => {
    progress[key] = 1;
    updateProgress();
  };

  const fontsReady = document.fonts?.ready
    .then(() => markComplete("fonts"))
    .catch(() => markComplete("fonts"))
    || Promise.resolve(markComplete("fonts"));

  const heroReady = new Promise((resolve) => {
    const hero = document.querySelector('img[fetchpriority="high"]');
    let complete = false;
    const finish = () => {
      if (complete) return;
      complete = true;
      markComplete("heroImage");
      resolve();
    };

    if (!hero) {
      finish();
    } else if (hero.complete && typeof hero.decode === "function") {
      hero.decode().then(finish).catch(finish);
    } else {
      hero.addEventListener("load", finish, { once: true });
      hero.addEventListener("error", finish, { once: true });
    }
  });

  const domReady = new Promise((resolve) => {
    const finish = () => {
      markComplete("domReady");
      resolve();
    };

    if (document.readyState === "complete") finish();
    else window.addEventListener("load", finish, { once: true });
  });

  const releasePage = ({ moveFocus = true } = {}) => {
    window.cancelAnimationFrame(frameId);
    preloader.classList.add("is-hidden");
    document.documentElement.classList.remove("is-loading");
    inertTargets.forEach((element) => { element.inert = false; });
    announcement.textContent = "The Bower has loaded";
    if (moveFocus) skipLink?.focus({ preventScroll: true });
  };

  paint();

  if (reducedMotion) {
    displayedProgress = 1;
    targetProgress = 1;
    paint();
    wait(80).then(() => releasePage({ moveFocus: false }));
    return;
  }

  frameId = window.requestAnimationFrame(tick);
  const realLoadComplete = Promise.all([fontsReady, heroReady, domReady]);

  Promise.race([
    Promise.all([realLoadComplete, wait(MIN_DISPLAY_MS)]),
    wait(FORCE_FINALIZE_MS)
  ]).then(async () => {
    finalizing = true;
    targetProgress = 1;

    await Promise.race([
      new Promise((resolve) => { settleResolver = resolve; }),
      wait(SETTLE_BUDGET_MS)
    ]);

    displayedProgress = 1;
    paint();
    preloader.classList.add("is-sealed");
    await wait(COMPLETE_HOLD_MS);
    preloader.classList.add("is-revealing");
    await wait(REVEAL_MS);
    releasePage();
  });
})();
