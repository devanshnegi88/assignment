import type { RescheduleSession } from "@/types/reschedule";
import { isPastSlot, isWithinLockout } from "./slot-utils";

export function getUpcomingSessions(sessions: RescheduleSession[]): RescheduleSession[] {
  return sessions
    .filter((session) => !isPastSlot(session.scheduledAt) && !isWithinLockout(session.scheduledAt))
    .sort((a, b) => new Date(a.scheduledAt).getTime() - new Date(b.scheduledAt).getTime())
    .slice(0, 3);
}
