# Debe Learning — Tech Intern Assessment

## Part 1 — GitHub Portfolio Walkthrough

### GitHub Profile

[GitHub Profile](https://github.com/devanshnegi88)

### Repository 1 — Golf Charity Platform

**Repository:**  
https://github.com/devanshnegi88/Golf--Charity--Platform

#### Problem It Solves

The Golf Charity Platform is a web application built around golf-related activities and charity participation.

#### What I Specifically Built

I worked on the parts of the application that I personally implemented, including backend functionality, database interactions, authentication, and payment-related functionality.

The project uses Supabase for authentication and PostgreSQL-backed data, with Supabase Edge Functions for server-side operations. Stripe is used for payment-related functionality.

One specific debugging task I worked on involved the login and registration flow, where asynchronous initialization could occur before required functions were available. I adjusted the initialization flow and added error handling.

#### Design Decision I Would Change Today

If I were rebuilding the project today, I would improve the frontend structure by separating application logic into smaller reusable modules.

This would make the application easier to maintain, test, and extend as more features are added.

### Repository 2 — Smart Study Assistant

**Repository:**  
[https://github.com/devanshnegi88/Smart-Study-Assistant]

#### Problem It Solves

The Smart Study Assistant is an AI-powered learning application designed to bring study planning, question answering, notes, quizzes, reminders, and progress tracking into a single application.

#### What I Specifically Built

I worked on the backend, database integration, API functionality, and AI-powered features that I personally implemented in the project.

The application uses Flask for the backend and MongoDB for data storage. The AI features include study planning, question answering, summarization, quizzes, and other learning workflows.

#### Design Decision I Would Change Today

If I were rebuilding the project today, I would separate the AI layer more clearly from the core application logic.

This would make it easier to change the AI provider or model without requiring changes throughout the rest of the application.

### Part 1 Recording

[Watch Part 1 ScreenPal Recording](https://go.screenpal.com/watch/cOjli5nv4v1)

---

## Part 2 — Debugging Round

### Files

The original assessment code is available in:

`PART-2-DEBUGGING/original.ts`

The corrected implementation is available in:

`PART-2-DEBUGGING/fixed.ts`

### Bug 1 — Async/Await

The original Firestore query uses `.get()` without awaiting the returned Promise.

The code then attempts to access `existing.docs` immediately.

#### Fix

The corrected implementation makes the callable function asynchronous and awaits the Firestore query before inspecting the returned snapshot.

#### Production Impact

Without waiting for the asynchronous query to complete, the function cannot reliably use the query result and can fail at runtime.

### Bug 2 — Firestore Write

The original implementation starts the Firestore booking write and immediately returns success.

#### Fix

The corrected implementation performs the write as part of an awaited transaction.

#### Production Impact

The caller could receive a successful response before the booking has actually been persisted.

### Bug 3 — Security

The original implementation trusts `studentId` supplied directly by the client.

#### Fix

The corrected implementation requires authentication and uses `context.auth.uid` as the student's identity.

#### Production Impact

A malicious caller could otherwise submit another student's ID and create a booking associated with someone else's account.

### Bug 4 — Concurrent Booking

The original implementation performs the availability check separately from creating the booking.

Two requests arriving at nearly the same time could both see the slot as available.

#### Fix

The corrected implementation uses a Firestore transaction so the availability check and booking creation happen atomically.

#### Production Impact

Without an atomic operation, concurrent requests could create duplicate bookings for the same teacher and slot.

### Implementation Notes

Each fix is documented directly above the relevant change in `fixed.ts` with an explanation of the production impact.

---

## Part 3 — Session Reschedule Widget

### Overview

The Session Reschedule Widget is a parent-facing tutoring scheduling feature built with Next.js, React, and TypeScript.

It displays the student's next three upcoming tutoring sessions and allows the parent to request a new date and time.

### Features

The widget provides:

- Three upcoming tutoring sessions
- Subject
- Teacher name
- Datetime
- Session status
- Request Reschedule action
- Date and time selection
- Reason selection
- Loading state
- Error state
- Success feedback

### Reschedule Reasons

The form provides the required options:

- Conflict
- Illness
- Time zone
- Other

### Request Flow

The frontend calls a locally mocked function named:

`requestReschedule`

No deployed Firebase project is required.

The function returns the following typed response:

```ts
{
  success: boolean;
  error?: string;
}
```



## Part 4 — Explain-It-Yourself Video

### Recording

[Watch the Part 4 Recording](https://www.loom.com/share/cb24f10b864b4840956f914bc2795191)

### Duration

Approximately 4–7 minutes.

### What I Demonstrate

The recording provides a live walkthrough of the Part 3 implementation and covers:

1. The upcoming tutoring sessions UI.
2. The Request Reschedule flow.
3. The reschedule form and reason selection.
4. Local time handling in the browser.
5. Conversion from local `datetime-local` input to UTC.
6. The two-hour tutoring lead-time restriction.
7. Validation for past and duplicate slots.
8. Loading, success, and error states.

### Local Time and UTC Explanation

The parent selects a date and time using their local browser timezone.

The selected `datetime-local` value does not contain an explicit timezone offset. The application interprets the value in the browser's local timezone and converts the resulting instant to a UTC ISO string before sending it through the reschedule flow.

For example, in an IST browser:

```text
Parent selects:
2026-08-22T05:00

UTC representation:
2026-08-21T23:30:00.000Z
Parent selects:
2026-08-22T05:00

UTC representation:
2026-08-21T23:30:00.000Z
```
