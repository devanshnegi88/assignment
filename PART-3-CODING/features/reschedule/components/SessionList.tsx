"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { TutoringSession } from "@/types/reschedule";
import RescheduleForm from "./RescheduleForm";

interface SessionCardProps {
  session: TutoringSession;
}

export default function SessionCard({ session: initialSession }: SessionCardProps): ReactElement {
  const [session, setSession] = useState(initialSession);
  const [isFormOpen, setIsFormOpen] = useState(false);

  // session.datetimeUtc is stored as a UTC ISO string. toLocaleString() renders
  // it in the browser's own local timezone -- this is the only place display
  // needs to think about timezones.
  const localDatetime = new Date(session.datetimeUtc).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  const statusBadgeClass =
    session.status === "confirmed"
      ? "status-badge status-badge--confirmed"
      : session.status === "reschedule_pending"
      ? "status-badge status-badge--pending"
      : "status-badge status-badge--cancelled";

  function handleRescheduleSuccess(newDatetimeUtc: string): void {
    // Optional local update so the parent sees the change immediately.
    setSession((current) => ({
      ...current,
      datetimeUtc: newDatetimeUtc,
      status: "reschedule_pending",
    }));
  }

  return (
    <article className="session-card">
      <h2>{session.subject}</h2>
      <p className="session-meta">Teacher: {session.teacherName}</p>
      <p className="session-meta">When: {localDatetime}</p>
      <p className="session-meta">
        <span className={statusBadgeClass}>{session.status}</span>
      </p>

      {!isFormOpen && (
        <button type="button" className="btn btn-primary" onClick={() => setIsFormOpen(true)}>
          Request Reschedule
        </button>
      )}

      {isFormOpen && (
        <RescheduleForm
          session={session}
          onCancel={() => setIsFormOpen(false)}
          onSuccess={handleRescheduleSuccess}
        />
      )}
    </article>
  );
}