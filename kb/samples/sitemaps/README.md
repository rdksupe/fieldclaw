# Sample site maps (GeoJSON)

Demo logistics plans the superintendent / AE would email into the project inbox.
Supervisor Claw should discover `*.geojson` during init and call:

```http
POST /api/projects/{id}/sitemap
Content-Type: application/geo+json
```

Coordinates in these samples are **site-local percent (0–100)** so the FieldClaw zone map can render without a CRS transform.

| File | Project flavor |
|------|----------------|
| `human-dc1-site-logistics.geojson` | Demo DC pad (site-local 0–100 coords): Structure / Electrical / Mechanical / White Space / Laydown / Site Office |
| `osm-nyc-construction-sites.geojson` | **Real** OSM `landuse=construction` polygons (NYC metro): WTC5, Hudson Yards casing, Wagner Park, Madison Ave, etc. Lon/lat — FieldClaw normalizes on import. ODbL. |
| `saguenay-chantiers511.geojson` | Real Québec open data roadworks (LineString) — good for mail realism, **not** for zone polygons |
