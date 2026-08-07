import { SessionRescheduleWidget } from "@/features/reschedule/components/SessionRescheduleWidget";
import { mockSessions } from "@/data/mock-sessions";
import { getUpcomingSessions } from "@/features/reschedule/lib/get-upcoming-sessions";

// Server Component: computing the "next 3" list here (server-side) means
// the client never receives sessions it shouldn't show, rather than
// fetching everything and filtering in the browser.
export default function HomePage(): JSX.Element {
  const upcomingSessions = getUpcomingSessions(mockSessions);

  return (
    <main>
      <h1>Session Reschedule Widget</h1>
      <SessionRescheduleWidget sessions={upcomingSessions} />
    </main>
  );
}