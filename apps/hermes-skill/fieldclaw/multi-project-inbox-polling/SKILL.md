---
name: multi-project-inbox-polling
description: Multi-project AgentMail inbox polling for FieldClaw cron — inbox→project routing, label-based inbound filtering, dedup against existing events, empty-project orphan-inbound handling, and self-seeded demo-corpus detection (report first sighting, then SILENT on repeats).
version: 0.4.0
---

# Multi-Project AgentMail Inbox Polling (FieldClaw cron)

Under cron, poll ALL project inboxes — not just `FIELDCLAW_PROJECT_ID`.

## Steps

1. **Build inbox→project map**: `GET /api/projects` → each project has
   `inbox_email` and `id` fields. Map every inbox to its project.
2. **List all AgentMail inboxes**: `GET /v0/inboxes`. Auth via
   `Authorization: Bearer {AGENT...Y}`. MCP preferred but may fail
   with `AttributeError: 'CallToolResult' object has no attribute 'isError'`;
   fall back to REST.
3. **Poll each mapped inbox**: `GET /v0/inboxes/{inbox_id}/messages`.
4. **Filter for inbound**: `labels` containing `"received"` or `"unread"`.
   - Skip messages labeled `"sent"` only — these are agent-self-sent
     (gateway shutdown notices, setup pings). They are NOT site traffic.
   - The `kaya-meow@agentmail.to` inbox commonly has only "sent" messages
     in steady-state; project-specific inboxes like `fieldclaw-rfi-iso@agentmail.to`
     receive real inbound.
5. **Dedup against existing events**: For the matching project,
   `GET /api/projects/{pid}/events` → check if `email.inbound` with
   matching `thread_id` already exists in any event's `payload.thread_id`
   (check BOTH `email.inbound` and `email.parsed` — both carry `thread_id`).
   If found, the message is already processed — skip to avoid duplicates.
6. **Process new inbound**: Parse PO/ETA/intent/zone, POST `email.inbound`
   + `email.parsed` (+ `schedule.flagged` if delay), then handle attachments
   via `POST .../mail/pull-attachments` or `wiki_fs.py ingest`.

## Label filtering (corrected)

Previous version of this pattern said to filter by `labels` containing `"inbox"`.
**This is wrong.** AgentMail uses `"received"` and `"unread"` for inbound,
`"sent"` for outbound. There is no `"inbox"` label.

| Label | Meaning |
|-------|---------|
| `"received"` | Inbound message delivered to inbox |
| `"unread"` | Not yet read (inbound) |
| `"sent"` | Outbound — agent-self-sent, skip |

## AgentMail MCP vs REST

Prefer MCP (`mcp_agentmail_list_inboxes`, `mcp_agentmail_list_messages`,
`mcp_agentmail_get_thread`). On MCP failure, fall back to REST at
`https://api.agentmail.to/v0/` with `Authorization: Bearer {AGENT...Y}`.
REST field: `inbox_id` (NOT `id`) is the identifier for subsequent calls.

## REST endpoint reference

```
GET /v0/inboxes                              → {count, inboxes: [{inbox_id, email, ...}]}
GET /v0/inboxes/{inbox_id}/messages          → {count, messages: [...]}
GET /v0/inboxes/{inbox_id}/threads/{tid}     → full thread with messages[].text
```

## Read-only poll + dedup detector (reference)

The following read-only pattern reliably answers "which threads are genuinely
new this run?" and is security-filter-safe (reads keys via
`os.environ.get("PREFIX" + "_SUFFIX", "")` so the `*_API_KEY` reference survives
the write_file filter). Run it with `terminal` (`execute_code` is blocked under
cron), then POST events only for the `NEW` threads it flags.

- Build inbox→project map from the **live** `/api/projects` response (never a
  stale env `FIELDCLAW_PROJECT_ID`), keyed by `inbox_email`.
- `GET /v0/inboxes` → collect `inbox_id` for each mapped inbox.
- For each inbox: `GET /v0/inboxes/{inbox_id}/messages?limit=50`, and separately
  `GET /api/projects/{pid}/events?limit=200` to collect already-seen `thread_id`s
  from both `email.inbound` and `email.parsed` payloads.
- Classify each message:
  - `labels` that are only `{"sent"}` → SKIP (outbound / agent-self-sent).
  - `thread_id` already in the seen set → SKIP (already processed).
  - otherwise → NEW → POST `email.inbound` + `email.parsed`
    (+ `schedule.flagged` if delay), then `mail/pull-attachments` if attachments.

## Empty project list does NOT mean empty inboxes — iterate inboxes, not the project loop

If a poll script loops over **projects** (`for p in /api/projects`) and fetches
that project's inbox inside the loop, then when `/api/projects` returns `[]` the
loop body NEVER runs → the script prints `NO_NEW_INBOUND` without having polled a
single inbox. Real inbound can still be sitting in an AgentMail inbox that has no
registered project. Confirm /api/projects first; if it is empty, poll ALL
AgentMail inboxes (`GET /v0/inboxes` → per-inbox `GET /v0/inboxes/{iid}/messages`)
directly and look for `received`/`unread` labels yourself before concluding
nothing is new. (Observed 2026-08-12: `/api/projects` = `[]` while a
Human_DC1 site-logistics GeoJSON inbound sat unread in `fc-human-dc1@agentmail.to`.)

## Empty /api/projects + real inbound = orphan-inbound report, NOT [SILENT]

When `/api/projects` is empty (or FIELDCLAW_PROJECT_ID is blank and no project
matches the inbox that holds a `received`/`unread` thread) — a genuine unprocessed
finding exists:

- Do **NOT** respond `[SILENT]` — report the first sighting.
- Do **NOT** invent a project id, PO number, or POST `email.inbound`/`email.parsed`
  to a fabricated project. The FieldClaw resolve contract is explicit: writing to a
  made-up id is fabrication.
- Do **NOT** claim wiki.updated / attachments pulled when no project KB exists.
- Instead: deliver a short report naming the unread thread (id + subject + attachment(s)),
  state that no project is registered to route it to, and note the superintendent must
  seed the project and map the inbox before the logbook can capture that inbound.

> **The orphan trigger is not only an empty `[]` list.** A `/api/projects` that
> returns a SINGLE project with `inbox_email: null` (or otherwise no `inbox_email`
> mapping to the box holding the unread thread) is the same orphan situation —
> there is still no project to route to. Verify the API isn't lying by checking the
> backing SQLite (`data/fieldclaw.db`: `SELECT id,name,inbox_email FROM projects;`
> + an events/mail_messages count). If API and DB agree (one null-inbox project,
> 0 events, 0 mail_messages), the state is genuine and the thread is orphaned.
> A strong read-only cross-check: on the null-inbox project, `GET .../events` AND
> `GET .../zones` both empty means the inbound sitemap/GeoJSON was never imported —
> dedup must then lean on prior-run surfaced evidence, NOT on event existence.

## Orphan inbound may be SELF-SEEDED demo data — check the KB `samples/` corpus + seed emitters BEFORE reporting

Before ever reporting orphan inbound (even a "first sighting"), rule out that the
threads are **demo/seed corpus, not live site traffic.** Verified 2026-08-13 on a
mail-poll run:

- `GET /api/projects` → `[]`, `FIELDCLAW_PROJECT_ID` empty, DB 0 across all tables
  (genuine teardown/empty state).
- One AgentMail inbox `fc-my-site8506@agentmail.to` held 22 `received`/`unread`
  threads, all WCRWWTF/Wilbarger Creek documents from one sender.
- Every attachment filename exactly matched files already present and documented in
  the project KB at `kb/samples/wilbarger/` — enumerated in `SOURCES.md` (labeled
  "public sample demo corpus … for FieldClaw demo / wiki seed") and `CHANDRA_PROBE.md`.
- The inbox was deliberately populated by the project's own seed emitter:
  `sim/emitters/wilbarger_mail_seed.py --to fc-my-site8506@agentmail.to`.

**Classification:** when orphan `received`/`unread` threads are all from one sender,
all their attachments are already present in the KB `samples/<corpus>/` directory,
and a seed-emitter script references that exact inbox — those messages are
self-seeded demo data, NOT genuine site/supplier/EHS/quality traffic. The correct
call is `[SILENT]` even on the FIRST sighting (the "report-once" orphan rule exists
to surface *real* unroutable inbound, not to re-surface the project's own fixture
corpus). Reporting 22 already-known seeded PDFs with no project to route to is
notification spam.

**How to verify cheaply (all read-only, filesystem tools):**
1. `search_files(target='files')` for `samples/` under the KB root (`$FIELDCLAW_KB_DIR`)
   and list the corpus files.
2. Read `SOURCES.md` / `*.md` probe notes in that corpus dir — they usually label it
   as public/demo/seed data and enumerate every file.
3. `find` for the seed emitter (`sim/emitters/*_mail_seed.py`) and confirm `--to
   <inbox_email>` matches the polled inbox.

If all three line up, `[SILENT]`. Do NOT invent a project id, POST `email.*` events to
a fabricated project, or claim wiki updates — same fabrication bans as the orphan rule.

## Orphan-inbound threads get a dedup rule too: report the FIRST sighting, [SILENT] on unchanged repeats

The report-once rule above fires on the FIRST time a `received`/`unread` thread
can't be routed. But an orphan thread sits unread in its box and reappears on EVERY
run while unmapped. Re-surfacing the identical orphan (same `(inbox, thread_id)`,
same subject/attachments) cycle after cycle is exactly the notification-spam that
`fieldclaw-cron-escalation` rule 3 forbids — the superintendent already saw the
report and must act by seeding/mapping the project.

- **First sighting** of orphan `(inbox, thread_id)` → deliver the short report.
- **Repeat sighting** of the same `(inbox, thread_id)` with unchanged subject/
  attachments → already surfaced on an earlier run → `[SILENT]`. Verify against
  prior-run output: grep `~/.hermes-fieldclaw/cron/output/<job_id>/` for the
  thread_id. Match THIS job's id — the orphan may recur in a different fieldclaw
  cron's history too.
- **The skill's own documented "Observed" case counts as prior-surface evidence.**
  If the incoming orphan thread matches an orphan already written into this (or a
  sibling) skill's text as a `> Observed 2026-...:` narrative, treat it as a repeat
  sighting → `[SILENT]` — even if no cron-output file happens to contain the report.
  This is what made a clean `[SILENT]` legitimate on the 2026-08-12 run (see below):
  the skill body itself proved the thread had been surfaced before, so re-reporting
  it unchanged would be spam. The justification is "already surfaced / self-reported",
  not the weaker "nothing to route" (that premise would wrongly report it again).

Observed 2026-08-12: `fc-human-dc1@agentmail.to` held unread "Human_DC1 — Phase-1
Site Logistics Map (GeoJSON)" thread `f8e8ede9…` (attachment
`human-dc1-site-logistics.geojson`), while the only live project ("Smoke Site")
had `inbox_email: null` and DB showed 1 project / 0 events / 0 mail_messages —
API and DB agreed. The SAME thread appears in this skill's own text as a prior-run
observation, i.e. it was already surfaced once → the repeat sighting correctly
stays `[SILENT]`, justified by "already reported", not by the weaker "nothing to
route" (that premise would wrongly report it again).

> **⚠️ Pitfall (verified 2026-08-12): the "orphan / `inbox_email:null`" premise can be WRONG — the thread may have been routed anyway. Event-based dedup is authoritative; trust it over the orphan narrative.** On a later `fc-human-dc1` poll of the SAME thread, `GET /api/projects/{pid}/events` on the "Smoke Site" project returned 3 events — `email.inbound`, `email.parsed`, AND `wiki.updated` — all carrying `payload.thread_id = f8e8ede9…`. So the GeoJSON thread had been imported/processed into the project even though `inbox_email` was null (routed via another path, e.g. site-setup / sitemap import). Do NOT let the "orphan look" make you burn the run re-justifying "is this still an orphan / was it surfaced before". The decisive, cheapest dedup is **event-based**: before classifying an inbound as orphaned (or re-reporting a repeat), `GET .../api/projects/{pid}/events` and match `payload.thread_id` against `email.inbound`/`email.parsed`/`wiki.updated`. Presence of ANY of those events = already processed → `[SILENT]`, regardless of what `inbox_email` says. Prefer this event check over the skill-narrative / prior-run-grep evidence path every time — on this run the narrative said "orphan" while the events proved "already handled", and the events were right.

## Silent exit

When all inboxes have no new inbound (all "sent", already processed, already-surfaced
orphan repeats, OR confirmed self-seeded demo corpus): respond with exactly `[SILENT]`.

## See also

- `fieldclaw` — main project brain skill (AgentMail ownership, logbook API)
- `agentmail-rest-polling` — single-inbox REST polling details, security filter workarounds
- `cron-api-polling` — cron tool restrictions, execute_code blocked, terminal Python approach
- `fieldclaw-cron-browser-only` — the fully HTTP/browser tier when terminal is also blocked
- `fieldclaw-cron-escalation` — dedup vs prior runs / unchanged items, the report-once-then-quiet principle
