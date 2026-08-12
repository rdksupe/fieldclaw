# Dedup: schedule.flagged covered by its own (po, task, zone) tuple

Observed 2026-08-12 (watch-supplier-delays, Human_DC1 / DC Campus Demo).

A projected `schedule.flagged` can be already-notified even when NEITHER its own id
NOR its `payload.source_event_id` appears in the `notify.sent`/`notify.failed`
trigger sets. The `notify.sent` for a rebar shortage stores the PO/task/zone at the
**top level** of BOTH the notify event and the flagged event it was created from.
Matching only on ids therefore reports `already_notified: false` and triggers a
spurious escalation.

## Concrete case

DC Campus Demo `schedule.flagged` c13b3788 / 9200e4fc (PO-9905 rebar) did not match
any trigger-event-id/source-event-id, but both matched `notify.sent` 5c8ac44d /
0d3aac88 on the shared top-level tuple
(po=031e6726, task=0cf6712f, zone=9b1b5d60). Correct call: already handled → [SILENT].

Human_DC1 (env target 81989611): `schedule.flagged` c6d7659f → origin 98be8d55 already
in notify.failed (e21e5258) AND notify.sent (3ed82697, telegram delivered) → [SILENT].

## Fix — include the candidate's own tuple in the dedup test

```python
src_id = (ev.get("payload", {}) or {}).get("source_event_id")
tpl = (ev.get("po_id"), ev.get("task_id"), ev.get("zone_id"))
already = (ev["id"] in notified_trigger_ids) or (src_id in notified_trigger_ids) \
       or (tpl in notified_tuples)
```

## Scan-width reminder

Supplier-delay signals often live on a different project than the env
`FIELDCLAW_PROJECT_ID` target (e.g. env=Human_DC1 held only the handled rebar
flagged event; the DC Campus Demo held the rebar + bolt shortage signals). Iterate
ALL projects (`GET /api/projects`), not just the resolved one, and apply the same
tuple+id dedup per project.
