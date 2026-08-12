# Chandra / Datalab probe — Wilbarger location map

Tried `POST https://www.datalab.to/api/v1/convert` with
`kb/samples/wilbarger/2020-8668_site-location-map.pdf` in `mode=accurate`
(2026-08-12). Submit succeeded (`request_id=JVfyCo2XLCle8__J33wqpQ`) but the
job stayed `processing` for >2 minutes (60 polls) without completing.

**Takeaway:** that PDF is a road **location map**, not a plant zone plot plan.
Even when OCR finishes, it will not yield process-area polygons. For FieldClaw
zones use:

- `kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson` (preferred), or
- a true site-plan PDF/PNG whose **filename** includes `site-plan` / `sitemap` /
  `zone-map` / `logistics` so `import_from_document` (Datalab/Chandra) runs and
  lays out inferred labels on a grid.

Pipeline: `POST /api/projects/{id}/sitemap/upload` or mail pull with a matching
filename.
