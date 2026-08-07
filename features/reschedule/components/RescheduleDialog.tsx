"use client";

import { useEffect, useRef, useState } from "react";
import type {
  RescheduleReason,
  RequestRescheduleResult,
} from "@/types/reschedule";
import { RESCHEDULE_REASON_LABELS } from "@/types/reschedule";
import { LOCKOUT_HOURS, validateRescheduleRequest } from "@/lib/reschedule-validation";
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
}: RescheduleDialogProps): JSX.Element {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [newSlot, setNewSlot] = useState("");
  const [reason, setReason] = useState<RescheduleReason>("conflict");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
      setNewSlot("");
      setReason("conflict");
      setError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  // Recomputed on every render rather than memoized — "now" needs to
  // stay current if the dialog is left open a while, and this is a few
  // Date arithmetic ops, not expensive enough to justify useMemo's
  // complexity for correctness that would otherwise go stale.
  const minSelectable = getMinSelectableLocalDateTime(LOCKOUT_HOURS);

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();

    // The UTC conversion happens here, once, at the boundary where the
    // value leaves "local input land" — everything downstream (client
    // validation, the function call) deals with an honest UTC ISO
    // string from this point on, not a local string that Date parsing
    // happens to treat as if it were.
    const newSlotUtc = toUtcIsoString(newSlot);

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
      onClose();
    } catch {
      // Network/unexpected failure, distinct from a validation failure —
      // still surfaced through the same error region so screen reader
      // users get one consistent place to listen for problems.
      setError("Something went wrong. Please try again.");
    } finally {
      // Always clears, whether the try block returned early, threw, or
      // completed — a bare `setIsSubmitting(false)` after the try/catch
      // would be skipped by the early `return` inside the failure branch.
      setIsSubmitting(false);
    }
  }

  // Native <dialog> fires 'cancel' before 'close' when dismissed via
  // ESC. Blocking it while a request is in flight prevents the dialog
  // from disappearing mid-submit — the user would have no way to see
  // whether their request actually went through.
  function handleDialogCancel(
    event: React.SyntheticEvent<HTMLDialogElement>,
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
      <form onSubmit={handleSubmit} aria-busy={isSubmitting}>
        <h2 id="reschedule-dialog-heading">Request Reschedule</h2>

        <div>
          <label htmlFor="new-slot">New date and time</label>
          {/*
            `min` is the native, always-enforced half of the 2-hour
            lockout — the browser itself refuses times before this, so
            it's not just a validation message shown after the fact.
            `min` must be local time (the input has no UTC concept);
            see getMinSelectableLocalDateTime's doc comment for why
            that function can't just call toISOString().
          */}
          <input
            id="new-slot"
            type="datetime-local"
            value={newSlot}
            min={minSelectable}
            onChange={(event) => setNewSlot(event.target.value)}
            disabled={isSubmitting}
            required
          />
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
    </dialog>
  );
}