import type { TutoringSession } from "@/types/reschedule";

/**
 * Static mock data standing in for a Firestore query. Dates are computed
 * relative to module-load time, not hardcoded ISO strings — a fixed date
 * like "2025-01-15" would silently become "all in the past" the moment
 * this repo is opened after that date, breaking the demo for anyone
 * reviewing it later (a hiring committee running this weeks from now).
 *
 * Deliberately includes one past session and one cancelled-but-future
 * session so getUpcomingSessions() has something real to filter out —
 * a mock list that's already exactly the 3 sessions you want to show
 * doesn't prove the filtering logic works.
 */
function hoursFromNow(hours: number): string {
  return new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
}

export const mockSessions: TutoringSession[] = [
  {
    id: "sess_1",
    subject: "Algebra II",
    teacherName: "Priya Shah",
    datetimeUtc: hoursFromNow(4),
    status: "confirmed",
  },
  {
    id: "sess_2",
    subject: "Chemistry",
    teacherName: "Daniel Ortiz",
    datetimeUtc: hoursFromNow(30),
    status: "confirmed",
  },
  {
    id: "sess_3",
    subject: "SAT Reading",
    teacherName: "Priya Shah",
    datetimeUtc: hoursFromNow(52),
    status: "reschedule_pending",
  },
  {
    id: "sess_4",
    subject: "Physics",
    teacherName: "Wei Zhang",
    datetimeUtc: hoursFromNow(100),
    status: "confirmed",
  },
  {
    id: "sess_5",
    subject: "Algebra II",
    teacherName: "Priya Shah",
    datetimeUtc: hoursFromNow(-20),
    status: "confirmed",
  },
  {
    id: "sess_6",
    subject: "Chemistry",
    teacherName: "Daniel Ortiz",
    datetimeUtc: hoursFromNow(10),
    status: "cancelled",
  },
];