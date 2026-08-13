---
name: fc-cron-temp-file-hygiene
description: FieldClaw cron temp-file hygiene for DATA payloads passed between tool calls — siblings clobber /tmp/*.json just as they do scripts, so keep fetch+dedup+verify in one in-memory script and re-fetch on a bad read. Companion to the write-locked fieldclaw-cron-temp-script-hygiene.
version: 0.1.0
---

# FieldClaw cron temp-DATA-file hygiene

The FieldClaw AgentMail poll pipeline often hands intermediate state between
separate tool calls by writing a JSON file to `/tmp` (e.g. `curl -o
/tmp/am_msgs.json`, or `json.dump(..., open('/tmp/am_msgs.json','w'))` in a fetch
script) and re-reading it later for dedup/verify. Concurrent FieldClaw cron
siblings share `/tmp`, so these DATA files are a collision surface exactly like
temp scripts (see the write-locked `fieldclaw-cron-temp-script-hygiene` skill).

## Observed failure (2026-08-12)

A fetch step wrote `/tmp/am_msgs.json`. A sibling subagent overwrote it before the
dedup step read it, so `json.load(open('/tmp/am_msgs.json'))['messages']` raised
`KeyError: 'messages'` — the dedup was broken and had to be re-done by re-fetching
fresh. Note this is a DIFFERENT clobber than the script one: the path collided on
an intermediate data file, not a runnable script.

## Guards

1. **Fold fetch + dedup + verify into ONE self-contained script** and keep the
   data in memory — write nothing to /tmp between steps. This shrinks the
   collision surface to zero for the internal handoff.
2. **If you must pass a data file, re-fetch it fresh in the consuming step**
   rather than trusting a file a sibling may have replaced. A one-off fetch script
   (GET inbox, messages, threads → dump fresh) is cheap.
3. **On a bad read** (`KeyError`, empty dict, garbled shape): re-fetch the endpoint
   and recompute. The file is untrustworthy, the API is not. Never guess at
   missing data.
4. Cross-step data passed by filename is the weak link. Keep it in one process'
   memory or re-fetch — never assume a `/tmp/am_*.json` survived unchanged.

## Relationship to other skills

- `fieldclaw-cron-temp-script-hygiene` (write-locked fieldclaw store) — same
  collision surface for runnable scripts; read-back-before-run guard there.
- `agentmail-rest-polling` (write-locked) / `agentmail-rest-response-shapes`
  (editable) — response-shape knowledge for the fetch step.
- This skill exists so the data-file lesson has an editable home; the curator may
  fold it into the write-locked script-hygiene skill.
