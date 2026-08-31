import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  getDay,
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
  const availabilityElement = document.querySelector("#availability-data");
  const availability = JSON.parse(availabilityElement.textContent);
  const monthLabel = widget.querySelector("[data-month-label]");
  const calendarGrid = widget.querySelector("[data-calendar-grid]");
  const previousButton = widget.querySelector("[data-calendar-previous]");
  const nextButton = widget.querySelector("[data-calendar-next]");
  const selectedDateLabel = widget.querySelector("[data-selected-date]");
  const timeSlots = widget.querySelector("[data-time-slots]");
  const partySize = widget.querySelector("[data-party-size]");
  const confirmButton = widget.querySelector("[data-reservation-confirm]");
  const status = widget.querySelector("[data-reservation-status]");

  const today = startOfDay(new Date());
  const lastBookableMonth = startOfMonth(addMonths(today, 6));
  const closedWeekdays = new Set(availability.closed_weekdays || []);
  const isClosed = (date) => closedWeekdays.has(getDay(date));
  const remainingDaysThisMonth = eachDayOfInterval({
    start: today,
    end: endOfMonth(today)
  });
  const startingMonth = remainingDaysThisMonth.some((day) => !isClosed(day))
    ? today
    : addMonths(today, 1);
  let visibleMonth = startOfMonth(startingMonth);
  let selectedDate = null;
  let selectedTime = null;

  const dateKey = (date) => format(date, "yyyy-MM-dd");

  const slotsForDate = (date) => (
    availability.overrides?.[dateKey(date)] || availability.default_slots || []
  );

  const announce = (message) => {
    status.textContent = "";
    window.requestAnimationFrame(() => {
      status.textContent = message;
    });
  };

  const renderTimes = () => {
    timeSlots.replaceChildren();
    confirmButton.disabled = !selectedDate || !selectedTime;

    if (!selectedDate) return;

    slotsForDate(selectedDate).forEach((slot) => {
      const button = document.createElement("button");
      const dot = document.createElement("span");
      const label = document.createElement("span");
      const isSelected = selectedTime?.time === slot.time;

      button.type = "button";
      button.className = "time-slot";
      button.dataset.state = slot.state;
      button.disabled = slot.state === "full";
      button.setAttribute("aria-pressed", String(isSelected));
      button.setAttribute("aria-label", `${slot.label}, ${slot.state}`);

      dot.className = "availability-dot";
      dot.setAttribute("aria-hidden", "true");
      label.textContent = slot.label;
      button.append(dot, label);

      button.addEventListener("click", () => {
        selectedTime = slot;
        renderTimes();
        announce(
          `${slot.label} selected for ${format(selectedDate, "EEEE, d MMMM")}. ` +
          `${slot.state === "limited" ? "Limited availability." : "Available."}`
        );
      });

      timeSlots.append(button);
    });
  };

  const selectDate = (date) => {
    selectedDate = date;
    selectedTime = null;
    const slots = slotsForDate(date);
    const unavailableCount = slots.filter((slot) => slot.state === "full").length;
    const availabilityMessage = slots.length === 0
      ? "No reservation times are available."
      : `${slots.length} times shown. ${unavailableCount} ${unavailableCount === 1 ? "is" : "are"} unavailable.`;
    selectedDateLabel.textContent = format(date, "EEEE, d MMMM");
    renderCalendar();
    renderTimes();
    announce(
      `${format(date, "EEEE, d MMMM")} selected. Choose an available time. ${availabilityMessage}`
    );
  };

  const renderCalendar = () => {
    monthLabel.textContent = format(visibleMonth, "MMMM yyyy");
    calendarGrid.replaceChildren();

    const intervalStart = startOfWeek(startOfMonth(visibleMonth));
    const intervalEnd = endOfWeek(endOfMonth(visibleMonth));
    const days = eachDayOfInterval({ start: intervalStart, end: intervalEnd });

    days.forEach((day) => {
      const button = document.createElement("button");
      const isOutside = !isSameMonth(day, visibleMonth);
      const isPast = isBefore(day, today);
      const unavailable = isOutside || isPast || isClosed(day);

      button.type = "button";
      button.className = "calendar-day";
      button.textContent = format(day, "d");
      button.disabled = unavailable;
      button.setAttribute("aria-label", `${format(day, "EEEE, d MMMM yyyy")}${isClosed(day) ? ", closed" : ""}`);
      button.setAttribute("aria-pressed", String(Boolean(selectedDate && isSameDay(day, selectedDate))));

      if (isOutside) button.classList.add("is-outside");
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

  previousButton.addEventListener("click", () => {
    visibleMonth = startOfMonth(subMonths(visibleMonth, 1));
    renderCalendar();
  });

  nextButton.addEventListener("click", () => {
    visibleMonth = startOfMonth(addMonths(visibleMonth, 1));
    renderCalendar();
  });

  confirmButton.addEventListener("click", () => {
    if (!selectedDate || !selectedTime) return;
    announce(
      `Table held for ${partySize.value} guests on ${format(selectedDate, "EEEE, d MMMM")} ` +
      `at ${selectedTime.label}. This portfolio demonstration did not send a live booking.`
    );
  });

  renderCalendar();
  renderTimes();
}
