---
name: fieldclaw-cron-temp-script-hygiene
description: FieldClaw cron temp-script hygiene — concurrent sibling subagents share /tmp and collide on basename even with suffixed names; the reliable guard is to read the script back after write and re-token on clobber, and to fold sweep/dedup/verify into one script. Complements fieldclaw-cron-http-only-polling and cron-api-polling.
version: 0.1.1
---

# FieldClaw cron temp-script hygiene

FieldClaw cron jobs routinely drop a small `/tmp/fc_*.py` script to run the
AgentMail poll + FieldClaw POST pipeline. Concurrent cron run rate-limit
siblings/subagents share the same `/tmp`, so temp scripts are a real collision
surface. Lessons verified 2026-08-12.

## Pitfall: suffixed names are NOT enough

Advice that says "just use a unique suffixed name" (`fc_poll_claw.py`,
`fc_poll_<project>.py`) is insufficient. In one sweep, ALL THREE scripts written
with distinct, human-unique suffixed basenames (`fc_poll_claw_mail.py`,
`fc_dump_clawmail.py`, `fc_verify_claw.py`) each returned the same warning:

    _warning: "... was modified by sibling subagent '...' but this agent never
    read it."

The warning fires on basename write-contention from any concurrent sibling
regardless of how unique the name looks to you.

## Reliable guard: read the file back before running

- Add a genuinely high-entropy token to the basename (a random suffix, not just a
  project/inbox word) to MINIMIZE — not eliminate — the clash.
- **Always `read_file` the script right after `write_file`, before executing.**
  In the 2026-08-12 run, 2 of 3 scripts still had MY bytes intact despite the
  sibling alert, so the warning is advisory — trust the read, not the warning.
  If the read shows sibling content, write to a fresh token name and re-verify.
- Fold dedup/sweep/dump/verify into a SINGLE poll script to shrink the number of
  /tmp files you create per run, reducing the collision surface.
- Clean intuition: the goal is to only ever run a script whose content you have
  personally confirmed, never one you assumed-survived.

## Pitfall: don't waste a tool call deleting the temp scripts at the end

There is no need to `rm -f /tmp/fc_*.py` as a cleanup step. In cron the delete can
trip an approval prompt (`... "delete in root path"` → `pending_approval`) and
block the run, with nothing gained — `/tmp` is ephemeral, the unique basenames
above already prevent collisions, and a fresh token name every run means stale
leftovers are harmless dross. Skip the cleanup entirely; spend zero tool calls on
it. (Observed 2026-08-12 supplier-delay poll.)

## Relationship to other skills

- `fieldclaw-cron-http-only-polling` — offline-resolve in browser_console, then
  /tmp mail script via terminal; shares this collision surface.
- `cron-api-polling` — /tmp-script pattern mechanics.
- `fieldclaw-cron-telegram-send`, `multi-project-inbox-polling` — other FieldClaw
  cron pipelines that also write /tmp scripts and should apply the same guard.

## Known tool constraint (why you may have to create rather than patch)

FieldClaw skills live under `~/.hermes-fieldclaw/skills/fieldclaw/<name>/`.
`skill_manage` patch/edit/write_file from the `default` profile fail with
"Skill not found in active profile" — only `action='create'` resolves on that
store. To refine an existing fieldclaw SKILL.md, edit the file directly on the
filesystem; if that tool is unavailable, log the lesson separately and let the
curator fold it in.
