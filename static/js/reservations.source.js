import {
  addDays,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isAfter,
  isBefore,
  isSameDay,
  isSameMonth,
  startOfDay,
  startOfMonth,
  startOfWeek,
  subMonths
} from "date-fns";

const widget = document.querySelector("[data-reservation-widget]");

if (widget) {
  const monthLabel = widget.querySelector("[data-month-label]");
  const calendarGrid = widget.querySelector("[data-calendar-grid]");
  const previousButton = widget.querySelector("[data-calendar-previous]");
  const nextButton = widget.querySelector("[data-calendar-next]");
  const selectedDateLabel = widget.querySelector("[data-selected-date]");
  const timeSlots = widget.querySelector("[data-time-slots]");
  const partySize = widget.querySelector("[data-party-size]");
  const reservationForm = widget.querySelector("[data-reservation-form]");
  const tableChoice = widget.querySelector("[data-table-choice]");
  const tableModes = [...widget.querySelectorAll("[data-table-mode]")];
  const floorPlan = widget.querySelector("[data-floor-plan]");
  const floorPlanCanvas = widget.querySelector("[data-floor-plan-canvas]");
  const tableDetail = widget.querySelector("[data-table-detail]");
  const reservationSummary = widget.querySelector("[data-reservation-summary]");
  const confirmButton = widget.querySelector("[data-reservation-confirm]");
  const successPanel = widget.querySelector("[data-reservation-success]");
  const confirmationSummary = widget.querySelector("[data-confirmation-summary]");
  const confirmationCode = widget.querySelector("[data-confirmation-code]");
  const status = widget.querySelector("[data-reservation-status]");

  const today = startOfDay(new Date());
  const lastBookableDate = addDays(today, 90);
  const lastBookableMonth = startOfMonth(lastBookableDate);
  let visibleMonth = startOfMonth(today);
  let selectedDate = null;
  let selectedSlot = null;
  let availableSlots = [];
  let floorPlanTables = [];
  let tableMode = "automatic";
  let selectedTableId = null;
  let availabilityRequest = 0;

  const dateKey = (date) => format(date, "yyyy-MM-dd");
  const announce = (message, state = "") => {
    status.dataset.state = state;
    status.textContent = "";
    window.requestAnimationFrame(() => { status.textContent = message; });
  };

  const emptyMessage = (message, loading = false) => {
    const paragraph = document.createElement("p");
    paragraph.className = `reservation-empty${loading ? " is-loading" : ""}`;
    paragraph.textContent = message;
    timeSlots.replaceChildren(paragraph);
  };

  const resetDetails = () => {
    selectedSlot = null;
    selectedTableId = null;
    tableChoice.hidden = true;
    floorPlan.hidden = true;
    reservationForm.hidden = true;
    successPanel.hidden = true;
  };

  const showDetails = () => {
    if (!selectedDate || !selectedSlot) return;
    if (tableMode === "map" && selectedTableId === null) {
      reservationForm.hidden = true;
      return;
    }
    reservationSummary.textContent = `${format(selectedDate, "EEEE, d MMMM")} at ${selectedSlot.label} · ${partySize.value} guests`;
    reservationForm.hidden = false;
    successPanel.hidden = true;
  };

  const sectionLabel = (section) => ({
    MAIN_DINING: "Main dining room",
    WINDOW: "Window seating",
    PRIVATE: "Private room",
    BAR: "Bar seating",
    TERRACE: "Terrace"
  })[section] || "Dining room";

  const renderFloorPlan = () => {
    floorPlanCanvas.querySelectorAll("button").forEach((button) => button.remove());
    if (!selectedSlot) return;
    const availableIds = new Set(selectedSlot.tables.map((table) => table.id));

    floorPlanTables.forEach((table) => {
      const available = availableIds.has(table.id);
      const state = table.capacity < Number(partySize.value)
        ? "too-small"
        : available
          ? (selectedTableId === table.id ? "selected" : "available")
          : "unavailable";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "floor-table";
      button.dataset.state = state;
      button.dataset.shape = table.shape.toLowerCase();
      button.style.setProperty("--table-x", `${table.x}%`);
      button.style.setProperty("--table-y", `${table.y}%`);
      button.disabled = !available;
      button.setAttribute("aria-pressed", String(selectedTableId === table.id));
      button.setAttribute("aria-label", `${table.name}, ${sectionLabel(table.section)}, seats up to ${table.capacity}${table.accessible ? ", accessible" : ""}, ${state.replace("-", " ")}`);
      button.innerHTML = `<span>${table.name.replace("Table ", "T").replace("Bar ", "B")}</span><small>${table.capacity}</small>`;
      button.addEventListener("focus", () => {
        tableDetail.textContent = `${table.name} · ${sectionLabel(table.section)} · Seats up to ${table.capacity}${table.accessible ? " · Accessible" : ""}`;
      });
      button.addEventListener("pointerenter", () => {
        tableDetail.textContent = `${table.name} · ${sectionLabel(table.section)} · Seats up to ${table.capacity}${table.accessible ? " · Accessible" : ""}`;
      });
      button.addEventListener("click", () => {
        selectedTableId = table.id;
        renderFloorPlan();
        showDetails();
        announce(`${table.name} selected. Add your details to confirm the reservation.`);
      });
      floorPlanCanvas.append(button);
    });
  };

  const showSeatingChoices = () => {
    tableChoice.hidden = false;
    floorPlan.hidden = tableMode !== "map";
    if (tableMode === "map") {
      renderFloorPlan();
      tableDetail.textContent = selectedTableId
        ? "Your selected table is outlined in brass."
        : "Select an outlined table.";
    }
    showDetails();
  };

  const renderTimes = () => {
    timeSlots.replaceChildren();
    if (!selectedDate) {
      emptyMessage("Choose a date to see live availability.");
      return;
    }
    if (availableSlots.length === 0) {
      emptyMessage("No tables are available for this date and party size.");
      return;
    }

    availableSlots.forEach((slot) => {
      const button = document.createElement("button");
      const dot = document.createElement("span");
      const label = document.createElement("span");
      const isSelected = selectedSlot?.startsAt === slot.startsAt;
      const limited = slot.availableTableCount <= 2;

      button.type = "button";
      button.className = "time-slot";
      button.dataset.state = limited ? "limited" : "available";
      button.setAttribute("aria-pressed", String(isSelected));
      button.setAttribute("aria-label", `${slot.label}, ${limited ? "limited availability" : "available"}`);
      dot.className = "availability-dot";
      dot.setAttribute("aria-hidden", "true");
      label.textContent = slot.label;
      button.append(dot, label);

      button.addEventListener("click", () => {
        selectedSlot = slot;
        selectedTableId = null;
        tableMode = "automatic";
        tableModes.forEach((mode) => { mode.checked = mode.value === "automatic"; });
        renderTimes();
        showSeatingChoices();
        announce(`${slot.label} selected. Choose a seating preference.`);
      });
      timeSlots.append(button);
    });
  };

  const fetchAvailability = async () => {
    if (!selectedDate) return;
    const requestId = ++availabilityRequest;
    resetDetails();
    availableSlots = [];
    emptyMessage("Checking the dining room…", true);
    announce("Loading availability.");

    try {
      const query = new URLSearchParams({date: dateKey(selectedDate), partySize: partySize.value});
      const response = await fetch(`/api/availability?${query}`, {headers: {Accept: "application/json"}});
      const payload = await response.json();
      if (requestId !== availabilityRequest) return;
      if (!response.ok) throw new Error(payload.message || "Availability could not be loaded.");

      availableSlots = payload.slots.map((slot) => ({
        ...slot,
        label: new Intl.DateTimeFormat(undefined, {hour: "numeric", minute: "2-digit"}).format(new Date(slot.startsAt))
      }));
      floorPlanTables = payload.floorPlan?.tables || [];
      renderTimes();
      announce(availableSlots.length
        ? `${availableSlots.length} reservation times are available. Choose a time.`
        : "No tables are available for this date and party size.",
        availableSlots.length ? "" : "notice");
    } catch (error) {
      if (requestId !== availabilityRequest) return;
      emptyMessage("We could not check availability. Please try again.");
      announce(error.message || "We could not check availability. Please try again.", "error");
    }
  };

  const selectDate = (date) => {
    selectedDate = date;
    selectedDateLabel.textContent = format(date, "EEEE, d MMMM");
    renderCalendar();
    fetchAvailability();
  };

  const renderCalendar = () => {
    monthLabel.textContent = format(visibleMonth, "MMMM yyyy");
    calendarGrid.replaceChildren();
    const days = eachDayOfInterval({
      start: startOfWeek(startOfMonth(visibleMonth)),
      end: endOfWeek(endOfMonth(visibleMonth))
    });

    days.forEach((day) => {
      const button = document.createElement("button");
      const outside = !isSameMonth(day, visibleMonth);
      const unavailable = outside || isBefore(day, today) || isAfter(day, lastBookableDate);
      button.type = "button";
      button.className = "calendar-day";
      button.textContent = format(day, "d");
      button.disabled = unavailable;
      button.setAttribute("aria-label", format(day, "EEEE, d MMMM yyyy"));
      button.setAttribute("aria-pressed", String(Boolean(selectedDate && isSameDay(day, selectedDate))));
      if (outside) button.classList.add("is-outside");
      if (isSameDay(day, today)) {
        button.classList.add("is-today");
        button.setAttribute("aria-current", "date");
      }
      button.addEventListener("click", () => selectDate(day));
      calendarGrid.append(button);
    });

    previousButton.disabled = !isAfter(visibleMonth, startOfMonth(today));
    nextButton.disabled = !isBefore(visibleMonth, lastBookableMonth);
  };

  const showConflictAlternatives = (alternatives) => {
    if (!alternatives?.length) return;
    availableSlots = alternatives.map((slot) => ({
      ...slot,
      label: new Intl.DateTimeFormat(undefined, {hour: "numeric", minute: "2-digit"}).format(new Date(slot.startsAt))
    }));
    resetDetails();
    renderTimes();
  };

  reservationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedDate || !selectedSlot || !reservationForm.reportValidity()) return;
    confirmButton.disabled = true;
    confirmButton.textContent = "Confirming…";
    announce("Confirming your reservation.");
    const formData = new FormData(reservationForm);
    const payload = {
      date: dateKey(selectedDate),
      time: selectedSlot.time,
      partySize: Number(partySize.value),
      tableId: selectedTableId || undefined,
      customer: {
        name: formData.get("name"),
        email: formData.get("email"),
        phone: formData.get("phone")
      },
      specialRequests: formData.get("specialRequests")
    };

    try {
      const response = await fetch("/api/reservations", {
        method: "POST",
        headers: {"Content-Type": "application/json", Accept: "application/json"},
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (response.status === 409) {
        showConflictAlternatives(result.alternatives);
        announce("That table has just been reserved. We can still seat you nearby—choose one of these times.", "error");
        return;
      }
      if (!response.ok) throw new Error(result.message || "We could not confirm the reservation.");

      reservationForm.hidden = true;
      successPanel.hidden = false;
      confirmationCode.textContent = result.reservation.confirmationCode;
      confirmationSummary.textContent = `${format(selectedDate, "EEEE, d MMMM")} at ${selectedSlot.label} for ${partySize.value} guests.`;
      announce("Reservation successfully confirmed.", "success");
      successPanel.focus();
    } catch (error) {
      announce(error.message || "We could not confirm the reservation. Please try again.", "error");
    } finally {
      confirmButton.disabled = false;
      confirmButton.textContent = "Confirm reservation";
    }
  });

  partySize.addEventListener("change", () => {
    if (selectedDate) fetchAvailability();
  });
  tableModes.forEach((mode) => mode.addEventListener("change", () => {
    tableMode = mode.value;
    selectedTableId = null;
    floorPlan.hidden = tableMode !== "map";
    renderFloorPlan();
    showDetails();
    announce(tableMode === "map"
      ? "Choose an available table from the dining room map."
      : "We will choose the most suitable available table for you.");
  }));
  previousButton.addEventListener("click", () => {
    visibleMonth = startOfMonth(subMonths(visibleMonth, 1));
    renderCalendar();
  });
  nextButton.addEventListener("click", () => {
    visibleMonth = startOfMonth(addDays(endOfMonth(visibleMonth), 1));
    renderCalendar();
  });

  renderCalendar();
  renderTimes();
}
