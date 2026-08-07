import type { TutoringSession } from "@/types/reschedule";
import { formatSessionDateTime } from "../lib/format-datetime";

interface SessionCardProps {
  session: TutoringSession;
  onRequestReschedule: (sessionId: string) => void;
}

export function SessionCard({
  session,
  onRequestReschedule,
}: SessionCardProps): JSX.Element {
  return (
    <li className="session-card">
      <div className="session-card__details">
        <p className="session-card__subject">{session.subject}</p>
        <p className="session-card__teacher">{session.teacherName}</p>
        {/*
          Resolves the Milestone 4 TODO: session.datetimeUtc is stored
          and passed around as UTC everywhere else in this app — this is
          the one place it gets converted for a human to read, via
          formatSessionDateTime (features/reschedule/lib/format-datetime.ts).
        */}
        <p className="session-card__datetime">
          {formatSessionDateTime(session.datetimeUtc)}
        </p>
        <p className="session-card__status">{session.status}</p>
      </div>
      <button type="button" onClick={() => onRequestReschedule(session.id)}>
        Request Reschedule
      </button>
    </li>
  );
}