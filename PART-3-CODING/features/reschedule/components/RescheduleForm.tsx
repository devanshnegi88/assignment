"use client";

import { useState, type FormEvent, type ReactElement } from "react";
import type {
  RescheduleReason,
  RequestRescheduleInput,
  RequestRescheduleResult,
  TutoringSession,
} from "@/types/reschedule";
import { requestReschedule } from "@/functions/requestReschedule";
import {
  getMinSelectableLocalDateTime,
  toUtcIsoString,
} from "@/features/reschedule/lib/format-datetime";

const RESCHEDULE_REASON_OPTIONS: Array<{
  value: RescheduleReason;
  label: string;
}> = [
  { value: "conflict", label: "Conflict" },
  { value: "illness", label: "Illness" },
  { value: "time_zone", label: "Time zone" },
  { value: "other", label: "Other" },
];

const MIN_LEAD_TIME_HOURS = 2;

type SubmitStatus = "idle" | "loading" | "success" | "error";

interface RescheduleFormProps {
  session: TutoringSession;
  onCancel: () => void;
  // Called after a successful reschedule so the parent list can update
  // the displayed datetime/status without a full page reload.
  onSuccess: (newDatetimeUtc: string) => void;
}

export default function RescheduleForm({
  session,
  onCancel,
  onSuccess,
}: RescheduleFormProps): ReactElement {
  const [newDatetimeLocal, setNewDatetimeLocal] = useState("");
  const [reason, setReason] = useState<RescheduleReason | "">("");
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const minSelectableLocal = getMinSelectableLocalDateTime(MIN_LEAD_TIME_HOURS);

  const canSubmit = newDatetimeLocal !== "" && reason !== "" && status !== "loading";

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();

    if (reason === "") {
      return;
    }

    setStatus("loading");
    setErrorMessage(null);

    try {
      const newDatetimeUtc = toUtcIsoString(newDatetimeLocal);

      const response: RequestRescheduleResult = await requestReschedule({
        sessionId: session.id,
        newSlotUtc: newDatetimeUtc,
        reason,
      });

      if (response.success) {
        setStatus("success");
        onSuccess(newDatetimeUtc);
      } else {
        setStatus("error");
        setErrorMessage(response.error ?? "The reschedule request could not be completed.");
      }
    } catch {
      // Never expose a raw stack trace to the parent.
      setStatus("error");
      setErrorMessage("Something went wrong while submitting your request. Please try again.");
    }
  }

  if (status === "success") {
    return (
      <div className="form-success" role="status">
        <p>Your reschedule request has been submitted.</p>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Close
        </button>
      </div>
    );
  }

  return (
    <form
      className="reschedule-form"
      onSubmit={handleSubmit}
      aria-label={`Reschedule ${session.subject} session`}
    >
      <div className="form-field">
        <label htmlFor={`datetime-${session.id}`}>New date &amp; time</label>
        <input
          id={`datetime-${session.id}`}
          type="datetime-local"
          value={newDatetimeLocal}
          min={minSelectableLocal}
          onChange={(event) => setNewDatetimeLocal(event.target.value)}
          disabled={status === "loading"}
          aria-describedby={`datetime-hint-${session.id}`}
          required
        />
        <p className="form-hint" id={`datetime-hint-${session.id}`}>
          Times shown are in your local timezone. Requests must be made at
          least 2 hours before the session.
        </p>
      </div>

      <div className="form-field">
        <label htmlFor={`reason-${session.id}`}>Reason</label>
        <select
          id={`reason-${session.id}`}
          value={reason}
          onChange={(event) => setReason(event.target.value as RescheduleReason)}
          disabled={status === "loading"}
          required
        >
          <option value="" disabled>
            Select a reason
          </option>
          {RESCHEDULE_REASON_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {status === "error" && errorMessage && (
        <p className="form-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
          {status === "loading" ? "Submitting..." : "Submit request"}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onCancel}
          disabled={status === "loading"}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}