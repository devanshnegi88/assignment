import * as functions from "firebase-functions";
import * as admin from "firebase-admin";

admin.initializeApp();
const db = admin.firestore();

interface BookingRequest {
  studentId: string;
  teacherId: string;
  slot: string; // ISO datetime string
  subject: string;
}

export const bookSession = functions.https.onCall(
  // BUG 3 (typing): `context` had no type annotation in the original code.
  // Under strict TypeScript (`noImplicitAny`) that's a compile error, and
  // even without strict mode it silently makes `context` an untyped `any`,
  // so a typo like `context.auht` would fail at runtime instead of at
  // compile time. Annotating it as `functions.https.CallableContext`
  // restores type checking and is what makes `context.auth` below safe
  // to use.
  async (data: BookingRequest, context: functions.https.CallableContext) => {
    // BUG 4 (security): the original function never checked `context.auth`,
    // so ANY caller -- authenticated or not -- could invoke it directly
    // (e.g. via the REST endpoint) and create a booking for an arbitrary
    // `studentId`. In production that allows spam bookings and lets one
    // user book, or impersonate, sessions on behalf of a different student.
    if (!context.auth) {
      throw new functions.https.HttpsError(
        "unauthenticated",
        "You must be signed in to book a session."
      );
    }
    if (context.auth.uid !== data.studentId) {
      throw new functions.https.HttpsError(
        "permission-denied",
        "You can only book sessions for your own account."
      );
    }

    const booking = {
      studentId: data.studentId,
      teacherId: data.teacherId,
      slot: data.slot,
      subject: data.subject,
      status: "confirmed",
      createdAt: new Date(),
    };

    const bookingsRef = db.collection("bookings");

    // BUG 1 (async/await): `.get()` returns a Promise<QuerySnapshot>, but
    // the original code never awaited it and the handler wasn't even
    // declared `async`. `existing` was therefore a pending Promise, not a
    // snapshot -- reading `existing.docs.length` would throw at runtime
    // ("Cannot read properties of undefined") rather than actually
    // checking anything.
    //
    // BUG 2 (logic): separately, the original existence check queried
    // `teacherRef.collection("bookings")` (a subcollection nested under
    // the teacher document) but the write went to the top-level
    // `db.collection("bookings")` -- two entirely different collections
    // that never overlap. Even with `await` added, the duplicate-booking
    // check could never find a match, so double-booking prevention was
    // dead code in production. The fix queries the *same* collection the
    // write targets, filtered by teacherId + slot.
    //
    // Checking-then-writing as two separate steps is also inherently
    // racy: two near-simultaneous requests for the same slot could both
    // pass the check before either has written. Wrapping the read and the
    // write in a single Firestore transaction closes that race window.
    const result = await db.runTransaction(async (transaction) => {
      const existing = await transaction.get(
        bookingsRef
          .where("teacherId", "==", data.teacherId)
          .where("slot", "==", data.slot)
      );

      if (!existing.empty) {
        return { success: false, message: "Slot already booked" };
      }

      const newBookingRef = bookingsRef.doc();
      transaction.set(newBookingRef, booking);
      return { success: true };
    });

    return result;
  }
);