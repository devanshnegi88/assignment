"use client";

import { useState, type ReactElement } from "react";
import type {
  RescheduleReason,
  RequestRescheduleResult,
  TutoringSession,
} from "@/types/reschedule";
import { requestReschedule } from "@/functions/requestReschedule";
import { getUpcomingSessions } from "../lib/get-upcoming-sessions";
import SessionCard from "./SessionCard";
import { RescheduleDialog } from "./RescheduleDialog";

interface SessionRescheduleWidgetProps {
  sessions: TutoringSession[];
}

/**
 * Client Component boundary: this needs local state (which session's
 * dialog is open) and event handlers, so it can't be a Server Component.
 * `app/page.tsx` stays a Server Component and passes `sessions` in as a
 * prop — the interactivity is pushed as far down the tree as it needs
 * to go, not hoisted onto the whole page.
 */
export function SessionRescheduleWidget({
  sessions,
}: SessionRescheduleWidgetProps): ReactElement {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Looked up rather than tracked as separate state — activeSessionId is
  // the single source of truth for "which session is being rescheduled";
  // deriving the session object from it means there's no way for the two
  // to drift out of sync.
  const activeSession =
    sessions.find((session) => session.id === activeSessionId) ?? null;

  const upcomingSessions = getUpcomingSessions(sessions);

  function handleRequestReschedule(sessionId: string): void {
    setActiveSessionId(sessionId);
  }

  function handleCloseDialog(): void {
    setActiveSessionId(null);
  }

  // Performs the operation and hands back the typed result — doesn't
  // decide what happens next. Whether to close (success) or show an
  // error (failure) is the dialog's call, since it owns that UI state.
  //
  // Resolves the last Milestone 6/7/8 TODO: the dialog now converts to
  // UTC before calling this (features/reschedule/components/RescheduleDialog.tsx),
  // so newSlotUtc arriving here is an honest UTC ISO string, not a
  // local one wearing the name.
  async function handleSubmitReschedule(
    newSlotUtc: string,
    reason: RescheduleReason,
  ): Promise<RequestRescheduleResult> {
    if (!activeSessionId) {
      return { success: false, error: "No session selected." };
    }
    return requestReschedule({
      sessionId: activeSessionId,
      newSlotUtc,
      reason,
    });
  }

  if (upcomingSessions.length === 0) {
    return (
      <section aria-labelledby="upcoming-sessions-heading">
        <h2 id="upcoming-sessions-heading">Upcoming Sessions</h2>
        <p>No upcoming sessions.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="upcoming-sessions-heading">
      <h2 id="upcoming-sessions-heading">Upcoming Sessions</h2>
      <ul className="session-list">
        {upcomingSessions.map((session) => (
          <li key={session.id}>
            <SessionCard
              session={session}
              onRequestReschedule={handleRequestReschedule}
            />
          </li>
        ))}
      </ul>
      <RescheduleDialog
        isOpen={activeSessionId !== null}
        currentSlotUtc={activeSession?.datetimeUtc ?? ""}
        onClose={handleCloseDialog}
        onSubmit={handleSubmitReschedule}
      />
    </section>
  );
}