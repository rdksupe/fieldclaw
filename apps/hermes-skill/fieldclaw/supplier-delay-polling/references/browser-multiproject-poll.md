# Compact multi-project poll in browser_console (HTTP-only resolve)

Verified 2026-08-12 on `watch-supplier-delays`. When the job spec forbids
terminal/eval/execute_code for the resolve step, the correct path is a
`browser_console` `fetch` carrying the `X-API-Key` header. Chain resolve +
all-project scan in ONE async IIFE so raw JSON never floods context.

## Why the histogram reduction matters

On noisy projects (e.g. the DC Campus Demo project returned **125 events** in
`events?limit=100`, mostly `sim.kaggle_site` safety/quality news), returning the
raw event array explodes context. Instead reduce each project to a compact
summary: queue item id/type/status and an event-type histogram with counts.

## The pattern

```js
(async () => {
  const key = "dev-key-change-me";            // read real key from env first
  const base = "http://127.0.0.1:8000";
  const j = async (p) => {
    const r = await fetch(base+p, { headers: {"X-API-Key": key} });
    try { return {status:r.status, body: await r.json()}; }
    catch(e){ return {status:r.status, body:"ERR "+ (await r.text()).slice(0,300)}; }
  };
  let out = {};
  for (const pid of PIDS) {
    const q  = await j(`/api/projects/${pid}/super-queue`);
    const ev = await j(`/api/projects/${pid}/events?limit=100`);
    out[pid] = {
      queue: Array.isArray(q.body) ? q.body.map(e => ({id:e.id,type:e.type,status:e.status,src:e.source,payload:e.payload})) : q.body,
      ev_count: Array.isArray(ev.body) ? ev.body.length : "n/a",
      types: Array.isArray(ev.body)
        ? ev.body.reduce((a,e)=>{a[e.type]=(a[e.type]||0)+1; return a;},{})
        : null
    };
  }
  return JSON.stringify(out);
})()
```

The `types` histogram is the highest-signal output: it immediately reveals
`notify.sent`/`notify.failed`/`schedule.flagged`/`shortage.reported` presence per
project without dumping every event. For a supplier-delay job you then drill into
just the supplier-relevant events (`notify.*`, `schedule.flagged`,
`email.inbound`/`email.parsed`, `status.reported` with shortage keywords) on the
projects that have them — filtered view, e.g.:

```js
const rel = ev.body.filter(e => ["notify.sent","notify.failed","schedule.flagged",
  "shortage.reported","email.inbound","email.parsed","status.reported"].includes(e.type))
  .map(e => ({id:e.id,type:e.type,created:e.created_at,source:e.source,
    po:e.po_id, task:e.task_id, zone:e.zone_id, payload:e.payload}));
```

## Key facts this run confirmed

- Env `FIELDCLAW_PROJECT_ID` (Human_DC1 `81989611...`) was valid; rebar
  `schedule.flagged c6d7659f` already had `notify.sent 3ed82697 delivered:true`
  msg 94 — handled. Non-shortage queue items (`safety.reported`, `status.reported`)
  stay out of scope for a shortage-scoped job.
- RFI Isolation `schedule.flagged d24ed7e8` had **empty payload `{}`** → skip per
  skill (malformed).
- DC Campus rebar `schedule.flagged c13b3788`/`9200e4fc` → `notify.sent`
  `5c8ac44d`/`0d3aac88`; bolt `status.reported e0daaef2` → `notify.failed
  3d90fdf7` with Test Admin having no real channel (telegram null + example
  email) = terminal dead-end, no re-attempt.
- Correct outcome: `[SILENT]` — nothing new.
