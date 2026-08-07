/**
 * FE-only display/wire-format conversion between UTC (how sessions are
 * stored and sent) and the browser's local time (how a parent reads
 * them). Pure — no React — so it's testable independent of rendering.
 *
 * This file is where the assessment's core constraint actually lives:
 * "show the parent's local time while storing the value in UTC."
 * Everywhere else in this codebase either stores/sends UTC or displays
 * local — nothing should silently mix the two, and every crossing
 * point is one of the three functions below.
 */

const LOCAL_DATETIME_INPUT_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

/**
 * Renders a UTC ISO datetime string in the browser's local time zone,
 * for display only. `timeZoneName: "short"` is deliberate, not
 * decorative — an unlabeled local time is exactly the ambiguity the
 * brief is testing for. A parent should never have to guess whether
 * "2:30 PM" is their time or the server's.
 */
export function formatSessionDateTime(utcIso: string): string {
  return new Date(utcIso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZoneName: "short",
  });
}

/**
 * Converts a native <input type="datetime-local"> value
 * ("YYYY-MM-DDTHH:mm", no offset) into an explicit UTC ISO string for
 * the wire. `new Date(...)` already parses a value in this exact
 * shape as local time (see the note in lib/reschedule-validation.ts),
 * so the conversion itself already happened at parse time — this
 * function's only job is to make that an explicit, named step
 * (`.toISOString()` always outputs UTC) instead of something that
 * happens implicitly wherever a Date object gets serialized.
 */
export function toUtcIsoString(localDateTimeInputValue: string): string {
  if (!LOCAL_DATETIME_INPUT_PATTERN.test(localDateTimeInputValue)) {
    throw new Error(
      `Expected a datetime-local value like "2026-08-10T14:30", got "${localDateTimeInputValue}".`,
    );
  }
  return new Date(localDateTimeInputValue).toISOString();
}

/**
 * The earliest selectable moment for the datetime-local input — "now
 * plus the lockout window" — expressed in the format the input's
 * `min` attribute requires. This is what turns the 2-hour lockout into
 * an actually-disabled range in the picker, not just a rule enforced
 * after the fact in validation.
 *
 * Built from local getters (getFullYear/getMonth/...), NOT from
 * `.toISOString()`. toISOString() always returns UTC — using it here
 * would silently reintroduce the exact bug this milestone exists to
 * prevent: the `min` boundary would be off by the browser's UTC
 * offset, disabling the wrong slots for anyone not in UTC+0.
 */
export function getMinSelectableLocalDateTime(
  lockoutHours: number,
  now: Date = new Date(),
): string {
  const boundary = new Date(now.getTime() + lockoutHours * 60 * 60 * 1000);
  const pad = (value: number): string => String(value).padStart(2, "0");

  const year = boundary.getFullYear();
  const month = pad(boundary.getMonth() + 1);
  const day = pad(boundary.getDate());
  const hours = pad(boundary.getHours());
  const minutes = pad(boundary.getMinutes());

  return `${year}-${month}-${day}T${hours}:${minutes}`;
}