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

export const bookSession = functions.https.onCall((data: BookingRequest, context) => {
  const booking = {
    studentId: data.studentId,
    teacherId: data.teacherId,
    slot: data.slot,
    subject: data.subject,
    status: "confirmed",
    createdAt: new Date(),
  };

  const teacherRef = db.collection("teachers").doc(data.teacherId);
  const existing = teacherRef.collection("bookings").where("slot", "==", data.slot).get();

  if (existing.docs.length > 0) {
    return { success: false, message: "Slot already booked" };
  }

  db.collection("bookings").add(booking);
  return { success: true };
});