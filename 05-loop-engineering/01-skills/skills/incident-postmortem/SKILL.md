---
name: incident-postmortem
description: Write a blameless postmortem from incident notes. Use when the user describes an outage or production incident and wants a write-up.
---

# Incident Postmortem

## Steps

1. Build a timeline from the notes, in UTC. Mark any time you had to infer.
2. Separate the trigger (what set it off) from the root cause (why it was possible).
3. Fill in `assets/template.md`.
4. Give every action item one owner role and one measurable outcome.

Keep it blameless: describe what systems and processes allowed, never who was at fault. Ask for missing facts instead of inventing them.
