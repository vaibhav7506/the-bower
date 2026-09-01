(() => {
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

  const hero = document.querySelector("[data-time-aware-hero]");
  if (hero) {
    const hour = new Date().getHours();
    hero.dataset.timePeriod = hour >= 7 && hour < 18 ? "day" : "evening";
  }

  document.querySelectorAll("[data-flip-card]").forEach((card) => {
    card.addEventListener("click", () => {
      const isFlipped = card.classList.toggle("is-flipped");
      card.setAttribute("aria-pressed", String(isFlipped));
    });
  });

  const firstMenuCard = document.querySelector("[data-flip-card]");
  const menuSection = document.querySelector("#menu");

  if (firstMenuCard && menuSection && !motionQuery.matches) {
    const menuObserver = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;

      window.setTimeout(() => {
        if (firstMenuCard.getAttribute("aria-pressed") === "false") {
          firstMenuCard.classList.add("is-flipped");
          firstMenuCard.setAttribute("aria-pressed", "true");
        }
      }, 500);

      menuObserver.disconnect();
    }, { threshold: 0.18 });

    menuObserver.observe(menuSection);
  }

  const submitJsonForm = async (form, endpoint, statusElement) => {
    if (!form.reportValidity()) return false;

    const submitButton = form.querySelector('[type="submit"]');
    const payload = Object.fromEntries(new FormData(form).entries());
    submitButton.disabled = true;
    statusElement.textContent = "Sending…";

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      statusElement.textContent = result.message;
      return response.ok;
    } catch (_error) {
      statusElement.textContent = "We couldn’t send that just now. Please try again.";
      return false;
    } finally {
      submitButton.disabled = false;
    }
  };

  const newsletterForm = document.querySelector("[data-newsletter-form]");
  const newsletterStatus = document.querySelector("[data-newsletter-status]");

  newsletterForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const wasSuccessful = await submitJsonForm(newsletterForm, "/api/newsletter", newsletterStatus);
    if (wasSuccessful) newsletterForm.reset();
  });

  const eventDialog = document.querySelector("[data-event-dialog]");
  const eventForm = document.querySelector("[data-event-form]");
  const eventStatus = document.querySelector("[data-event-status]");
  const eventDate = eventForm?.querySelector('[name="event_date"]');

  if (eventDate) {
    const localToday = new Date();
    localToday.setMinutes(localToday.getMinutes() - localToday.getTimezoneOffset());
    eventDate.min = localToday.toISOString().slice(0, 10);
  }

  document.querySelector("[data-open-events]")?.addEventListener("click", () => {
    eventDialog?.showModal();
  });

  document.querySelector("[data-close-events]")?.addEventListener("click", () => {
    eventDialog?.close();
  });

  eventDialog?.addEventListener("click", (event) => {
    if (event.target === eventDialog) eventDialog.close();
  });

  eventForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const wasSuccessful = await submitJsonForm(eventForm, "/api/private-events", eventStatus);
    if (wasSuccessful) eventForm.reset();
  });

  const finePointer = window.matchMedia(
    "(hover: hover) and (pointer: fine) and (min-width: 1024px)"
  );
  const cursor = document.querySelector("[data-cursor]");

  if (cursor && finePointer.matches && !motionQuery.matches) {
    document.body.classList.add("has-custom-cursor");

    let pointerX = -100;
    let pointerY = -100;
    let cursorX = -100;
    let cursorY = -100;

    const renderCursor = () => {
      cursorX += (pointerX - cursorX) * 0.18;
      cursorY += (pointerY - cursorY) * 0.18;
      cursor.style.transform = `translate3d(${cursorX}px, ${cursorY}px, 0)`;
      requestAnimationFrame(renderCursor);
    };

    window.addEventListener("pointermove", (event) => {
      pointerX = event.clientX;
      pointerY = event.clientY;
    }, { passive: true });

    document.querySelectorAll("[data-framed-media]").forEach((frame) => {
      frame.addEventListener("pointerenter", () => cursor.classList.add("is-viewing"));
      frame.addEventListener("pointerleave", () => cursor.classList.remove("is-viewing"));
    });

    document.querySelectorAll('[data-cursor-theme="candle"]').forEach((section) => {
      section.addEventListener("pointerenter", () => cursor.classList.add("is-candle"));
      section.addEventListener("pointerleave", () => cursor.classList.remove("is-candle"));
    });

    requestAnimationFrame(renderCursor);
  }
})();
