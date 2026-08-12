
## `PART-4/README.md`


```md
# Part 4 — Explain-It-Yourself Video

## Recording

[Watch the Recording](https://www.loom.com/share/cb24f10b864b4840956f914bc2795191)

## Overview

The recording demonstrates the Session Reschedule Widget from Part 3 through a live code walkthrough.

## What the Recording Covers

### Part 3 Walkthrough

The recording demonstrates:

- Upcoming tutoring sessions
- Request Reschedule flow
- Reschedule form
- Validation
- Loading state
- Error handling
- Success handling

### Local Time and UTC

The recording explains:

- Why the parent interacts with local time
- Why UTC is used for the application wire/storage representation
- How the local `datetime-local` value is converted to UTC
- Why the conversion is important when users are in different timezones

### Two-Hour Lead-Time

The recording explains:

- How the two-hour boundary is calculated
- Why slots inside that window are disabled
- Why the same rule is validated by the reschedule function

### Intentional Debugging Demonstration

The timezone conversion is intentionally disabled during the recording.

The normal conversion:

```text
new Date(localDateTimeInputValue).toISOString()