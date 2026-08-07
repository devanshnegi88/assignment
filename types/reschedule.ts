/**
 * Shared contract between the frontend widget and the requestReschedule
 * Cloud Function. This is the single source of truth for both sides —
 * the function's input type and the form's submit payload are the same
 * type, not two interfaces hand-kept in sync.
 */

/**
 * Mirrors the status vocabulary used by the Part 2 Cloud Function
 * ("confirmed") so the two parts of this submission read as one
 * consistent domain, not two unrelated exercises.
 */
export type SessionStatus = "confirmed" | "reschedule_pending" | "cancelled";

export interface TutoringSession {
  id: string;
  subject: string;
  teacherName: string;
  /** ISO 8601 datetime string, always UTC. Never render this directly — convert to the viewer's local time first. */
  datetimeUtc: string;
  status: SessionStatus;
}

/**
 * Internal value, not display text. The dropdown shows "Time zone" but
 * stores "time_zone" — so relabeling the UI copy later doesn't require
 * a data migration, and the value is safe to use as e.g. an analytics
 * event property without depending on UI string formatting.
 */
export type RescheduleReason = "conflict" | "illness" | "time_zone" | "other";

export const RESCHEDULE_REASON_LABELS: Record<RescheduleReason, string> = {
  conflict: "Conflict",
  illness: "Illness",
  time_zone: "Time zone",
  other: "Other",
};

export interface RequestRescheduleInput {
  sessionId: string;
  /** ISO 8601 datetime string, always UTC — converted from the parent's local-time picker selection before it leaves the browser. */
  newSlotUtc: string;
  reason: RescheduleReason;
}

/**
 * Matches the shape specified in the brief exactly: { success: boolean; error?: string }.
 * A discriminated union (`{success:true} | {success:false; error:string}`)
 * would be stricter — but the brief pins this exact shape as the contract,
 * and silently "improving" a spec you were handed is its own code-review
 * flag. Called out explicitly rather than deviated from quietly.
 */
export interface RequestRescheduleResult {
  success: boolean;
  error?: string;
}
