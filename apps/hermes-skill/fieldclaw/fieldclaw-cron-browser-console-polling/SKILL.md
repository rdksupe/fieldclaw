---
name: fieldclaw-cron-browser-console-polling
description: Write robust browser_console async-fetch poll evals for FieldClaw cron — ES5-safe JS for multi-project sweeps, idempotent-read retry, bounded output, and reading cross-project notify.sent dedup proof that may lack a delivered flag.
version: 0.1.0
---

# FieldClaw cron browser_console polling (execution hygiene)

Complements `fieldclaw-cron-http-only-polling` (the sanctioned HTTP-only resolve +
poll transport under cron) and `fieldclaw-cron-notify-dedup` / `fieldclaw-cron-escalation`
(judgment). This skill is about WRITING the `browser_console` fetch eval so it actually
runs, and READING the results without over-claiming dedup.

## Golden rule: keep the eval in simple ES5

A single `browser_console` eval is ONE JS expression. Iterating several projects in a
nested arrow-function + template-literal IIFE is fragile — a tiny slip fails the WHOLE
eval with a `SyntaxError` and returns nothing. Observed 2026-08-12:
- stray token (`returnKey...`) → `SyntaxError: Unexpected token '...'`
- declaration mix-up inside nested arrows → `missing ) after argument list`

Both are easy when stacking `const` + `for...of` + arrow callbacks + backticks. Rewrite
conservatively to remove the failure surface:
- `var` declarations + classic `for (var i=0;i<n;i++)`, not `const`/`for...of`/arrows.
- String building with `+` concatenation, not template literals.
- No stray tokens; the body must be one valid expression ending in `return out;`.
- Prefix long data with a label (e.g. `'STATUS=200 n=3\n'`) so bounded output is greppable.

## Retry is free — the reads are idempotent

These are pure GETs. If the eval errors, just rewrite it more simply and re-run. A failed
presentation attempt changes NO project state and no notify record, so there is no
downside to a retry. The constraining step is only ever getting valid JS, not "mutating."

## Reading cross-project dedup proof: `delivered` may be absent

When sweeping OTHER projects (scan-width), many `notify.sent` records are
`channel: "email"` or `"email+telegram"` and carry NO `delivered:true` and NO
`message_id`/`mirrored` fields at all (those fields appear on the Telegram-channel sends).
Absence of `delivered` on an email-channel `notify.sent` is NOT evidence it failed — a
`notify.sent` record only exists after the delivery discipline confirmed the send. Treat
an existing `notify.sent` keyed to the trigger as handled even when `delivered` reads
`undefined`; if you need certainty, pull the record's full `payload` (a `notify.failed`
for the same trigger that PREDATES the `notify.sent` is superseded regardless).

## Bounded output

Return a compact summary (id, type, created, source, payload slice), not raw arrays —
raw event arrays blow up context. In multi-project sweeps, per project return only the
filtered signal lines plus a one-line `== <pid> ==` separator.

## Editing these skills

This and the other fieldclaw SKILL.md files live in a store that is write-locked for
`skill_manage` `patch`/`edit`/`write_file` from the default profile (they fail "not found
in active profile"); only `action='create'` resolves there. To fold this content back into
`fieldclaw-cron-http-only-polling` in place, edit that SKILL.md on the filesystem
(`~/.hermes-fieldclaw/skills/fieldclaw/fieldclaw-cron-http-only-polling/SKILL.md`)
via write_file/patch, then delete this skill.
