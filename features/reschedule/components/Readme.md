# features/reschedule

Feature-sliced module for the Session Reschedule Widget. Everything a parent
touches to view sessions and request a reschedule lives under this one
feature folder, instead of being scattered across generic `components/` and
`utils/` buckets at the project root.

## Why feature-sliced, not type-sliced

A type-sliced layout (`components/`, `hooks/`, `lib/` at the project root)
scales badly past one feature: you can't tell what belongs to what, and
deleting a feature means hunting across five folders. This project only has
one feature today, but the assessment is explicitly evaluating structure,
not just working code — so it's organized the way it would stay organized
at feature #5.

## Planned contents

| Path          | Owns                                                              | Lands in    |
|---------------|--------------------------------------------------------------------|-------------|
| `components/` | `SessionList`, `RescheduleDialog` — presentational + container UI
| `lib/`        | FE-only pure functions: UTC⇄local formatting for display, etc. | `features/reschedule/lib/` |

**Corrections from the original plan, made as each turned out to be
wrong rather than carried forward:**
- **`data/` moved to project root.** `mock-sessions.ts` stands in for a
  Firestore collection — the mocked Cloud Function (Milestone 8) needs
  to read it too, to look up a session's *actual* current slot rather
  than trusting whatever the client claims. Living inside
  `features/reschedule/` would repeat the same wrong dependency
  direction caught below. See `/data/mock-sessions.ts`.
- **`hooks/` was never populated.** The plan called for a
  `useRescheduleForm` hook, but the form state (slot, reason, error) is
  only ever used by `RescheduleDialog` itself — extracting a hook with
  one caller is indirection with no payoff. It'd be justified the
  moment a second component needed the same state shape; that hasn't
  happened, so it stays inline.
- **Validation rules moved to project root** (`/lib/reschedule-validation.ts`),
  not `features/reschedule/lib/` — same reasoning as `data/`: the
  mocked Cloud Function needs to call the same rules the dialog does,
  so they can't live inside a frontend-only folder.

`features/reschedule/lib/` (Milestone 9) stays reserved for genuinely
FE-only concerns — display formatting the function will never need.

## Shared types

Types used by both this feature and the mocked Cloud Function live in
`/types` at the project root, not in here — a Cloud Function shouldn't
import from inside a frontend feature folder, and vice versa. See
`/types/reschedule.ts`.