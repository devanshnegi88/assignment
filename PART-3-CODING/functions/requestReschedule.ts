import type {
  RequestRescheduleInput,
  RequestRescheduleResult,
} from "@/types/reschedule";
import { validateRescheduleRequest } from "../features/reschedule/lib/reschedule-validation";
import { mockSessions } from "../features/reschedule/data/mock-sessions";

const SIMULATED_LATENCY_MS = 600;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mocked stand-in for a Firebase Callable Cloud Function — the brief
 * says this doesn't need to be deployed. Shaped so the real onCall
 * handler is a thin wrapper someday: swap this body for a Firestore
 * read/write and the call signature at the frontend doesn't change.
 * The artificial delay isn't decoration — it forces the caller to
 * actually handle an async boundary instead of a same-tick resolved
 * promise that would hide a missing await or a missing loading state.
 *
 * Deliberately does NOT accept currentSlotUtc as a parameter from the
 * caller. A real Cloud Function must never trust the client's claim
 * about a record's current state — that's the same trust boundary
 * mistake being tested for in Part 2. This looks the session up
 * itself (here: the mock array; in production:
 * db.collection("bookings").doc(sessionId).get()) and validates
 * against what it finds. The dialog's client-side check in Milestone 7
 * is UX only — this re-validation is the actual boundary.
 */
export async function requestReschedule(
  input: RequestRescheduleInput,
): Promise<RequestRescheduleResult> {
  await delay(SIMULATED_LATENCY_MS);

  const session = mockSessions.find((s) => s.id === input.sessionId);
  if (!session) {
    return { success: false, error: "Session not found." };
  }

  const result = validateRescheduleRequest(
    input.newSlotUtc,
    session.datetimeUtc,
  );
  if (!result.valid) {
    return { success: false, error: result.error };
  }

  // A real implementation writes the updated slot and an audit record
  // here. Out of scope per the brief — this stub only validates.
  return { success: true };
}