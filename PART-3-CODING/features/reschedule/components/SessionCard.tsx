"use client";

import type { ReactElement } from "react";
import type { TutoringSession } from "@/types/reschedule";

interface SessionCardProps {
  session: TutoringSession;
  onRequestReschedule: (sessionId: string) => void;
}

export default function SessionCard({
  session,
  onRequestReschedule,
}: SessionCardProps): ReactElement {
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
  return (
    <article className="session-card">
      <h2>{session.subject}</h2>
      <p className="session-meta">Teacher: {session.teacherName}</p>
      <p className="session-meta">When: {localDatetime}</p>
      <p className="session-meta">
        <span className={statusBadgeClass}>{session.status}</span>
      </p>

      <button
        type="button"
        className="btn btn-primary"
        onClick={() => onRequestReschedule(session.id)}
      >
        Request Reschedule
      </button>
    </article>
  );
}