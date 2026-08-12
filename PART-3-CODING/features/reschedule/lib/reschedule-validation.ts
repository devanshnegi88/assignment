/**
 * Debe's real tutoring lead-time policy: a session can't be moved into
 * a slot less than this many hours out.
 */
export const LOCKOUT_HOURS = 2;

/**
 * True if `slotUtc` is at or before `now`.
 *
 * `slotUtc` here does not have to actually contain a "Z"/offset suffix
 * to be handled correctly: `new Date(dateTimeString)` parses an ISO-ish
 * string *with* a time component and *without* an offset as local wall-
 * clock time (per the ES2015+ Date Time String Format spec), and one
 * *with* a "Z" as UTC — either way it resolves to a correct absolute
 * instant. That's why this function is correct whether it's called with
 * the raw <input type="datetime-local"> value (Milestone 6/7) or a
 * proper UTC ISO string (post–Milestone 9) — the epoch comparison
 * doesn't care which representation it started as.
 */
export function isInPast(slotUtc: string, now: Date = new Date()): boolean {
  return new Date(slotUtc).getTime() <= now.getTime();
}

/**
 * True if the requested slot is the session's current slot. Submitting
 * a "reschedule" to the time it's already booked for isn't a
 * reschedule — it's a no-op that would otherwise silently report
 * success and confuse the teacher-side calendar.
 */
export function isIdenticalToCurrentSlot(
  newSlotUtc: string,
  currentSlotUtc: string,
): boolean {
  return (
    new Date(newSlotUtc).getTime() === new Date(currentSlotUtc).getTime()
  );
}

/**
 * True if `slotUtc` falls inside the lead-time lockout window.
 *
 * Kept as a separate check from isInPast on purpose: a slot 90 minutes
 * from now is not in the past, but it IS inside the lockout window —
 * they're different failures with different user-facing explanations,
 * so collapsing them into one boolean would lose information the
 * caller needs to explain *why* to the parent.
 */
export function isWithinLockoutWindow(
  slotUtc: string,
  now: Date = new Date(),
  lockoutHours: number = LOCKOUT_HOURS,
): boolean {
  const lockoutBoundaryMs = now.getTime() + lockoutHours * 60 * 60 * 1000;
  return new Date(slotUtc).getTime() < lockoutBoundaryMs;
}

export interface RescheduleValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Single entry point combining all three rules, checked in the order a
 * parent would find most useful: obviously-wrong (past) first, then the
 * policy-driven one that needs explaining (lockout), then the one
 * that's really a UI bug if it ever fires (identical slot). This
 * ordering is deliberate — it decides which message a user sees when
 * more than one rule fails at once.
 *
 * This same function is called from both the dialog (client-side, fast
 * feedback) and the mocked Cloud Function (Milestone 8) — client-side
 * validation is UX, never the actual security/data boundary, so the
 * function re-runs it rather than trusting what the client already
 * checked.
 */
export function validateRescheduleRequest(
  newSlotUtc: string,
  currentSlotUtc: string,
  now: Date = new Date(),
): RescheduleValidationResult {
  if (isInPast(newSlotUtc, now)) {
    return { valid: false, error: "The selected time has already passed." };
  }
  if (isWithinLockoutWindow(newSlotUtc, now)) {
    return {
      valid: false,
      error: `Sessions must be rescheduled at least ${LOCKOUT_HOURS} hours in advance.`,
    };
  }
  if (isIdenticalToCurrentSlot(newSlotUtc, currentSlotUtc)) {
    return { valid: false, error: "That's already the session's current time." };
  }
  return { valid: true };
}