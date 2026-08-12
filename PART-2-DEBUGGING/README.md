# Part 2 — Debugging Round

## Overview

This part contains the Firebase Cloud Functions and TypeScript debugging task from the assessment.

The original function is preserved in:

- [`original.ts`](./original.ts)

The corrected implementation is:

- [`fixed.ts`](./fixed.ts)

## Issues Identified

### 1. Async/Await

The Firestore `get()` operation is asynchronous, but the original implementation attempts to access the query result before the Promise resolves.

The corrected implementation awaits the Firestore query before inspecting the returned snapshot.

### 2. Firestore Write

The original implementation starts the booking write and immediately returns success.

The corrected implementation waits for the database operation to complete before returning success.

### 3. Security

The original implementation trusts the `studentId` supplied by the client.

The corrected implementation uses the authenticated user's identity from `context.auth`.

### 4. Concurrent Booking

The original availability check and booking creation can race when multiple requests arrive at the same time.

The corrected implementation uses an atomic transaction so that the availability check and booking creation happen together.

## Production Impact

Each fix includes a comment directly above the relevant code in `fixed.ts`, explaining why the issue matters in production.

## Assessment Files

### Original

`original.ts`

Contains the assessment's supplied implementation.

### Fixed

`fixed.ts`

Contains the corrected implementation with production-focused comments.

## Detailed Answers

The complete written explanation for Part 2 is also included in [`SUBMISSION.md`](../SUBMISSION.md).