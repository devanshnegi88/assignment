# Part 3 — Session Reschedule Widget

## Overview

A parent-facing tutoring session rescheduling widget built with **Next.js, React, and TypeScript**.

The feature simulates a tutoring portal workflow without requiring a deployed Firebase project.

## Features

- Displays the student's next 3 upcoming tutoring sessions
- Shows subject
- Shows teacher name
- Shows datetime
- Shows session status
- Request Reschedule action
- Date and time selection
- Reschedule reason selection
- Loading state
- Error state
- Success feedback

## Reschedule Reasons

The form provides the required options:

- Conflict
- Illness
- Time zone
- Other

## Request Flow

The frontend calls the locally mocked:

`requestReschedule`

No deployed Firebase project is required.

The function returns:

```text
{
  success: boolean;
  error?: string;
}