"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactElement,
  type SyntheticEvent,
} from "react";
import type {
  RescheduleReason,
  RequestRescheduleResult,
} from "@/types/reschedule";
import { RESCHEDULE_REASON_LABELS } from "@/types/reschedule";
import { LOCKOUT_HOURS, validateRescheduleRequest } from "../lib/reschedule-validation";
import {
  getMinSelectableLocalDateTime,
  toUtcIsoString,
} from "../lib/format-datetime";

interface RescheduleDialogProps {
  isOpen: boolean;
  currentSlotUtc: string;
  onClose: () => void;
  onSubmit: (
    newSlotUtc: string,
    reason: RescheduleReason,
  ) => Promise<RequestRescheduleResult>;
}

const REASON_OPTIONS = Object.entries(RESCHEDULE_REASON_LABELS) as Array<
  [RescheduleReason, string]
>;

/**
 * Native <dialog>, not a hand-rolled div + backdrop. showModal() gives us
 * focus trapping, ESC-to-close, and an inert background for free — the
 * rest of the page becomes unclickable while this is open, per the HTML
 * spec, with no extra JS. A div-based modal would need a focus-trap
 * library to match this correctly.
 *
 * Setting the `open` attribute declaratively does NOT get any of that
 * behavior — only the imperative showModal()/close() calls do, which is
 * why this is synced via a ref + effect instead of `<dialog open={isOpen}>`.
 */
export function RescheduleDialog({
  isOpen,
  currentSlotUtc,
  onClose,
  onSubmit,
}: RescheduleDialogProps): ReactElement {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [newDate, setNewDate] = useState("");
  const [newTime, setNewTime] = useState("");
  const [reason, setReason] = useState<RescheduleReason>("conflict");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasSubmitted, setHasSubmitted] = useState(false);

  useEffect(() => {
    const dialogEl = dialogRef.current;
    if (!dialogEl) return;
    if (isOpen && !dialogEl.open) {
      dialogEl.showModal();
    } else if (!isOpen && dialogEl.open) {
      dialogEl.close();
    }
  }, [isOpen]);

  // Reset form state each time the dialog opens — otherwise a stale
  // error message or a previously typed slot from session A could
  // still be showing when the parent opens the dialog for session B.
  useEffect(() => {
    if (isOpen) {
      setNewDate("");
      setNewTime("");
      setReason("conflict");
      setError(null);
      setIsSubmitting(false);
      setHasSubmitted(false);
    }
  }, [isOpen]);

  const minSelectableLocal = getMinSelectableLocalDateTime(LOCKOUT_HOURS);
  const minSelectableDate = minSelectableLocal.slice(0, 10);
  const minSelectableTime = minSelectableLocal.slice(11);
  const isSameDayAsBoundary = newDate === minSelectableDate;
  const minTimeForSelectedDate = isSameDayAsBoundary ? minSelectableTime : "00:00";

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();

    if (!newDate || !newTime) {
      setError("Please select both a date and time.");
      return;
    }

    const localDateTime = `${newDate}T${newTime}`;

    // The UTC conversion happens here, once, at the boundary where the
    // value leaves "local input land" — everything downstream (client
    // validation, the function call) deals with an honest UTC ISO
    // string from this point on, not a local string that Date parsing
    // happens to treat as if it were.
    const newSlotUtc = toUtcIsoString(localDateTime);

    const clientCheck = validateRescheduleRequest(newSlotUtc, currentSlotUtc);
    if (!clientCheck.valid) {
      setError(clientCheck.error ?? "That time isn't available.");
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      const result = await onSubmit(newSlotUtc, reason);
      if (!result.success) {
        setError(result.error ?? "Something went wrong. Please try again.");
        return;
      }
      setHasSubmitted(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  // Native <dialog> fires 'cancel' before 'close' when dismissed via
  // ESC. Blocking it while a request is in flight prevents the dialog
  // from disappearing mid-submit — the user would have no way to see
  // whether their request actually went through.
  function handleDialogCancel(
    event: SyntheticEvent<HTMLDialogElement>,
  ): void {
    if (isSubmitting) {
      event.preventDefault();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onCancel={handleDialogCancel}
      aria-labelledby="reschedule-dialog-heading"
    >
      {hasSubmitted ? (
        <div className="form-success" role="status">
          <h2 id="reschedule-dialog-heading">Reschedule Requested</h2>
          <p>Your reschedule request has been submitted successfully.</p>
          <button type="button" onClick={onClose} disabled={isSubmitting}>
            Close
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} aria-busy={isSubmitting}>
          <h2 id="reschedule-dialog-heading">Request Reschedule</h2>

          <div>
            <label htmlFor="new-date">New date</label>
            <input
              id="new-date"
              type="date"
              value={newDate}
              min={minSelectableDate}
              onChange={(event) => setNewDate(event.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div>
            <label htmlFor="new-time">New time</label>
            <input
              id="new-time"
              type="time"
              value={newTime}
              min={newDate ? minTimeForSelectedDate : "00:00"}
              onChange={(event) => setNewTime(event.target.value)}
              disabled={isSubmitting || !newDate}
              required
            />
            <p className="form-hint">
              Times are shown in your local timezone and converted to UTC before
              the request is sent.
            </p>
          </div>

          <div>
            <label htmlFor="reason">Reason</label>
            <select
              id="reason"
              value={reason}
              onChange={(event) =>
                setReason(event.target.value as RescheduleReason)
              }
              disabled={isSubmitting}
            >
              {REASON_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {isSubmitting && (
            <p role="status" className="reschedule-dialog__status">
              Submitting your request…
            </p>
          )}

          {error && (
            <p role="alert" className="reschedule-dialog__error">
              {error}
            </p>
          )}

          <div>
            <button type="button" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Submitting…" : "Submit"}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}