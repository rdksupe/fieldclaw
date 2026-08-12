# Browser-console compact multi-project poll (cron, no-shell-for-resolve spec)

When the job spec mandates `resolve via HTTP only — do NOT use
terminal/eval/execute_code` (cron cannot approve shell), the standard path is
`browser_navigate` to the base URL, then run a single `browser_console` IIFE that
chains resolve + poll. The trap is context flood: `fetch`ing `/api/projects/{id}/events`
raw for 4 projects dumps hundreds of JSON records into the conversation. Filter in JS
so the console returns only what the escalation decision needs.

## The pattern

Do everything in ONE console call so no raw JSON crosses a round-trip:

1. Resolve: `fetch(base + "/api/projects")` → confirm the env `FIELDCLAW_PROJECT_ID`
   still exists and identify it (don't trust the env string — match by id).
2. Poll: for every project, `fetch(base + "/api/projects/{id}/events?limit=100")`
   (NOT 500 — noisy-project timeout).
3. In JS, map each project's events down to an array of compact records:
   - Keep ONLY the event types you act on + the dedup types: for this job
     `["schedule.flagged","email.inbound","email.parsed","notify.sent","notify.failed"]`.
   - Pull `id, type, source, po_id, task_id, zone_id, created_at` and ONLY the payload
     keys the judgment needs: `summary, subject, intent, has_delay`, delivered flag,
     `trigger_event_id, source_event_id, super_queue_id, reason, error, channel, severity,
     status, message_id`. None of the free-text body/summary unless required.
4. Wrap each project fetch in try/catch and push `{project, error}` on failure — one
   project timing out must NOT abort the whole scan (matches the `limit=100` timeout
   guidance).
5. `return JSON.stringify(out)`.

## Why it matters for dedup (not just size)

Extracting `trigger_event_id`, `source_event_id`, `super_queue_id`, and the top-level
`po_id/task_id/zone_id` tuple in the SAME pass means you can apply all three dedup
handles (id-chain, super_queue_id↔event-id, tuple) without a second round-trip.

## Key

Substitute the real key into the JS (read from env via `echo $FIELDCLAW_API_KEY`).
Do NOT hardcode/guess it (wrong guess or the masked `***` → 401).

## Minimal skeleton

```js
(async () => {
  const key = "<REAL_KEY_FROM_ENV>";
  const base = "http://127.0.0.1:8000";
  const projects = [{id: "<pid>", name: "<name>"}, /* all from /api/projects */];
  const TYPES = ["schedule.flagged","email.inbound","email.parsed","notify.sent","notify.failed"];
  const KEYS = ["summary","subject","intent","has_delay","delivered","trigger_event_id",
    "source_event_id","super_queue_id","reason","error","channel","severity","status","message_id"];
  const out = [];
  for (const p of projects) {
    try {
      const r = await fetch(base + "/api/projects/" + p.id + "/events?limit=100",
        { headers: { "X-API-Key": key } });
      const evs = await r.json();
      const rel = evs.filter(e => TYPES.includes(e.type)).map(e => {
        const pk = {};
        for (const k of KEYS) if (e.payload && e.payload[k] !== undefined) pk[k] = e.payload[k];
        return { id: e.id, type: e.type, source: e.source, po_id: e.po_id,
                 task_id: e.task_id, zone_id: e.zone_id, created: e.created_at, payload: pk };
      });
      out.push({ project: p.name, id: p.id, total: evs.length, relevant: rel });
    } catch (err) { out.push({ project: p.name, id: p.id, error: String(err) }); }
  }
  return JSON.stringify(out);
})()
```

Then judge escalation from the compact output (see `fieldclaw-cron-escalation` escalation
rules + `fieldclaw-cron-notify-dedup` handles), and cross-check super-queue + the job's
own prior output in `~/.hermes-fieldclaw/cron/output/<job_id>/` before going `[SILENT]`.
