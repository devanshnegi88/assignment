import type { TutoringSession } from "@/types/reschedule";

const DEFAULT_LIMIT = 3;

/**
 * Returns the next `limit` upcoming sessions: excludes anything already
 * in the past and anything cancelled, sorted soonest first.
 *
 * `now` is a parameter with a default, not `new Date()` called inside
 * the function body — callers (and tests) can pass a fixed instant and
 * get a deterministic result, instead of the result depending on
 * whatever moment the test happens to run.
 */
export function getUpcomingSessions(
  sessions: TutoringSession[],
  now: Date = new Date(),
  limit: number = DEFAULT_LIMIT,
): TutoringSession[] {
  const nowMs = now.getTime();

  return sessions
    .filter((session) => session.status !== "cancelled")
    .filter((session) => new Date(session.datetimeUtc).getTime() > nowMs)
    .sort(
      (a, b) =>
        new Date(a.datetimeUtc).getTime() - new Date(b.datetimeUtc).getTime(),
    )
    .slice(0, limit);
}