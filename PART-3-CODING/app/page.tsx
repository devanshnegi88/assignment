import type { ReactElement } from "react";
import { mockSessions } from "@/features/reschedule/data/mock-sessions";
import { SessionRescheduleWidget } from "@/features/reschedule/components/SessionRescheduleWidget";

export default function Home(): ReactElement {
  return (
    <main className="page">
      <header className="page-header">
        <h1>Session Reschedule</h1>
        <p>Upcoming tutoring sessions</p>
      </header>
      <SessionRescheduleWidget sessions={mockSessions} />
    </main>
  );
}