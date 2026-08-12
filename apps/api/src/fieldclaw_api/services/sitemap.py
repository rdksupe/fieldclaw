"""Ingest GeoJSON / KML-ish FeatureCollections into FieldClaw zones."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from fieldclaw_api.models import Event, Project, Task, Zone
from fieldclaw_api.services import projects as projects_svc
from fieldclaw_api.services import wiki_layout


def _ring_to_xy(ring: list) -> list[list[float]]:
    out: list[list[float]] = []
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        out.append([float(pt[0]), float(pt[1])])
    # drop closing duplicate
    if len(out) >= 2 and out[0] == out[-1]:
        out = out[:-1]
    return out


def _feature_polygon(geom: dict[str, Any]) -> list[list[float]] | None:
    gtype = (geom or {}).get("type")
    coords = (geom or {}).get("coordinates")
    if not coords:
        return None
    if gtype == "Polygon":
        return _ring_to_xy(coords[0])
    if gtype == "MultiPolygon":
        # largest ring by vertex count
        rings = [_ring_to_xy(poly[0]) for poly in coords if poly]
        rings = [r for r in rings if len(r) >= 3]
        if not rings:
            return None
        return max(rings, key=len)
    return None


def _label_for(props: dict[str, Any], idx: int) -> str:
    for key in ("name", "label", "Name", "NAME", "zone", "title"):
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    code = props.get("code") or props.get("id")
    if code:
        return f"Zone {code}"
    return f"Zone {idx + 1}"


def _needs_normalize(polys: list[list[list[float]]]) -> bool:
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    if not xs:
        return False
    # site-local percent already → no normalize
    return not (
        min(xs) >= -5 and max(xs) <= 105 and min(ys) >= -5 and max(ys) <= 105
    )


def _normalize_to_map(
    polys: list[list[list[float]]], pad: float = 5.0
) -> list[list[list[float]]]:
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    usable = 100.0 - 2 * pad

    def map_pt(x: float, y: float) -> list[float]:
        # flip Y so north-up GIS still reads top-of-map as higher on canvas
        mx = pad + (x - min_x) / span_x * usable
        my = pad + (1.0 - (y - min_y) / span_y) * usable
        return [round(mx, 2), round(my, 2)]

    return [[map_pt(p[0], p[1]) for p in poly] for poly in polys]


def parse_geojson(data: dict[str, Any] | list | bytes | str) -> list[dict[str, Any]]:
    if isinstance(data, (bytes, bytearray)):
        data = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        data = json.loads(data)

    features: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            features = list(data.get("features") or [])
        elif data.get("type") == "Feature":
            features = [data]
        elif data.get("type") in ("Polygon", "MultiPolygon"):
            features = [{"type": "Feature", "properties": {}, "geometry": data}]
    elif isinstance(data, list):
        features = data

    parsed: list[dict[str, Any]] = []
    raw_polys: list[list[list[float]]] = []
    meta: list[dict[str, Any]] = []
    for i, feat in enumerate(features):
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        if not isinstance(props, dict):
            props = {}
        poly = _feature_polygon(feat.get("geometry") or {})
        if not poly or len(poly) < 3:
            continue
        raw_polys.append(poly)
        meta.append({"label": _label_for(props, i), "props": props})

    if not raw_polys:
        return []

    if _needs_normalize(raw_polys):
        raw_polys = _normalize_to_map(raw_polys)

    for m, poly in zip(meta, raw_polys, strict=True):
        parsed.append({"label": m["label"], "polygon": poly, "properties": m["props"]})
    return parsed


_SITEMAP_HINTS = (
    "sitemap",
    "site-map",
    "site_map",
    "site-logistics",
    "site_logistics",
    "logistics",
    "zone-map",
    "zone_map",
    "zones",
    "geojson",
    "site-plan",
    "site_plan",
    "plot-plan",
    "plot_plan",
)


def is_sitemap_filename(name: str) -> bool:
    """True for GeoJSON logistics maps and PDF/image site plans meant for zone import."""
    low = name.lower()
    stem_hint = any(h in low for h in _SITEMAP_HINTS)
    if low.endswith(".geojson"):
        return True
    if low.endswith(".json") and stem_hint:
        return True
    return bool(
        low.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"))
        and stem_hint
    )


def _extract_geojson_fence(text: str) -> dict[str, Any] | None:
    """Pull a FeatureCollection from OCR markdown / ```json fences."""
    import re

    for m in re.finditer(
        r"```(?:json|geojson)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.I
    ):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") in (
            "FeatureCollection",
            "Feature",
            "Polygon",
            "MultiPolygon",
        ):
            return obj
    # bare FeatureCollection blob
    idx = text.find('"FeatureCollection"')
    if idx >= 0:
        start = text.rfind("{", 0, idx)
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                ch = text[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[start : i + 1])
                            if (
                                isinstance(obj, dict)
                                and obj.get("type") == "FeatureCollection"
                            ):
                                return obj
                        except json.JSONDecodeError:
                            break
    return None


_ZONE_LINE = re.compile(
    r"(?im)^(?:[-*•]\s+)?(?:zone\s*)?([A-Za-z][\w /&-]{1,48})\s*(?:[—\-:]\s*(.+))?$"
)
_KNOWN_AREAS = (
    "influent",
    "headworks",
    "screening",
    "grit",
    "aeration",
    "blower",
    "ras",
    "was",
    "uv",
    "disinfection",
    "effluent",
    "biosolids",
    "solids",
    "laboratory",
    "ops",
    "operations",
    "maintenance",
    "electrical",
    "generator",
    "laydown",
    "logistics",
    "yard",
)


def labels_from_ocr(markdown: str, *, max_zones: int = 16) -> list[dict[str, str]]:
    """Heuristic zone labels from Chandra/Datalab markdown of a site plan."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in markdown.splitlines():
        s = line.strip()
        if len(s) < 3 or len(s) > 80:
            continue
        low = s.lower()
        if not any(k in low for k in _KNOWN_AREAS) and not low.startswith("zone"):
            continue
        m = _ZONE_LINE.match(s.lstrip("#").strip())
        label = (m.group(1).strip() if m else s.lstrip("#*-• ").strip())[:64]
        use = (m.group(2).strip() if m and m.group(2) else "")[:120]
        key = label.lower()
        if key in seen or key in ("figure", "project", "sheet", "drawing"):
            continue
        seen.add(key)
        found.append({"name": label, "use": use})
        if len(found) >= max_zones:
            break
    return found


def grid_feature_collection(labels: list[dict[str, str]]) -> dict[str, Any]:
    """Lay out N labels as approximate rectangles on the 0–100 canvas."""
    n = max(len(labels), 1)
    cols = 3 if n > 4 else (2 if n > 1 else 1)
    rows = (n + cols - 1) // cols
    pad_x, pad_y = 3.0, 3.0
    cell_w = (100.0 - pad_x * (cols + 1)) / cols
    cell_h = (100.0 - pad_y * (rows + 1)) / rows
    features = []
    for i, lab in enumerate(labels):
        r, c = divmod(i, cols)
        x0 = pad_x + c * (cell_w + pad_x)
        y0 = pad_y + r * (cell_h + pad_y)
        x1, y1 = x0 + cell_w, y0 + cell_h
        ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": lab.get("name") or f"Zone {i + 1}",
                    "use": lab.get("use") or "from site-plan OCR",
                    "code": lab.get("code") or f"Z{i + 1}",
                    "source": "ocr-grid",
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return {
        "type": "FeatureCollection",
        "properties": {
            "title": "Zones inferred from site-plan OCR",
            "coordinate_space": "site-local percent (0–100)",
            "note": "Approximate layout — refine via GeoJSON when available",
        },
        "features": features,
    }


def import_from_document(
    db: Session,
    project_id: str,
    data: bytes,
    *,
    filename: str,
    replace: bool = True,
) -> dict[str, Any]:
    """OCR a PDF/image site plan (Datalab/Chandra) → GeoJSON zones.

    Prefer embedded FeatureCollection in the OCR text; else heuristic labels
    laid out on a grid. Always stores OCR markdown under wiki/sources/.
    """
    from fieldclaw_api.services import datalab_svc
    from fieldclaw_api.services import projects as projects_svc

    project = db.get(Project, project_id)
    if not project:
        raise ValueError("project not found")

    root = projects_svc.kb_root_for(project)
    wiki_layout.ensure_wiki_layout(root)
    src_dir = root / "wiki" / "sources"
    maps_dir = root / "wiki" / "maps"
    src_dir.mkdir(parents=True, exist_ok=True)
    maps_dir.mkdir(parents=True, exist_ok=True)
    raw_path = src_dir / Path(filename).name
    raw_path.write_bytes(data)
    # Same file under maps/ for the Wiki → Maps tab gallery
    (maps_dir / Path(filename).name).write_bytes(data)

    md, engine = datalab_svc.pdf_to_markdown(raw_path)
    md_path = src_dir / f"{raw_path.stem}.ocr.md"
    md_path.write_text(md, encoding="utf-8")

    geo = _extract_geojson_fence(md)
    method = "embedded-geojson"
    if not geo:
        labels = labels_from_ocr(md)
        if not labels:
            # fallback: generic 4-zone pad so map is never empty after a plan ingest
            labels = [
                {"name": "Process area", "use": "from site plan OCR"},
                {"name": "Electrical / I&C", "use": "from site plan OCR"},
                {"name": "Ops / admin", "use": "from site plan OCR"},
                {"name": "Laydown", "use": "from site plan OCR"},
            ]
            method = "ocr-fallback-grid"
        else:
            method = "ocr-labels-grid"
        geo = grid_feature_collection(labels)

    result = import_geojson(
        db,
        project_id,
        geo,
        replace=replace,
        source_name=filename,
    )
    result["ocr_engine"] = engine
    result["ocr_method"] = method
    result["ocr_markdown"] = f"wiki/sources/{md_path.name}"
    return result


def import_geojson(
    db: Session,
    project_id: str,
    payload: dict[str, Any] | bytes | str,
    *,
    replace: bool = True,
    source_name: str | None = None,
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("project not found")

    zones_spec = parse_geojson(payload)
    if not zones_spec:
        raise ValueError("no Polygon features found in GeoJSON")

    removed = 0
    if replace:
        # Null FKs first — events/tasks may reference zones
        zone_ids = [
            zid
            for (zid,) in db.query(Zone.id).filter(Zone.project_id == project_id).all()
        ]
        if zone_ids:
            db.query(Event).filter(Event.zone_id.in_(zone_ids)).update(
                {Event.zone_id: None}, synchronize_session=False
            )
            db.query(Task).filter(Task.zone_id.in_(zone_ids)).update(
                {Task.zone_id: None}, synchronize_session=False
            )
        removed = db.query(Zone).filter(Zone.project_id == project_id).delete()
        db.commit()

    created = []
    root = projects_svc.kb_root_for(project)
    wiki_layout.ensure_wiki_layout(root)
    zones_dir = root / "wiki" / "zones"
    zones_dir.mkdir(parents=True, exist_ok=True)

    for spec in zones_spec:
        z = Zone(
            project_id=project_id,
            label=spec["label"],
            polygon_json=json.dumps(spec["polygon"]),
            status="grey",
            progress_pct=0.0,
        )
        db.add(z)
        db.flush()
        slug = re.sub(r"[^a-z0-9]+", "-", z.label.lower()).strip("-") or "zone"
        zpath = zones_dir / f"{slug}.md"
        props = spec.get("properties") or {}
        use = props.get("use") or props.get("description") or ""
        zpath.write_text(
            f"# {z.label}\n\n"
            f"Imported from site logistics map"
            f"{f' (`{source_name}`)' if source_name else ''}.\n\n"
            f"- code: {props.get('code', '—')}\n"
            f"- use: {use or '—'}\n"
            f"- status: {z.status}\n"
            f"- progress: {z.progress_pct}%\n\n"
            f"See [[ops/log]] for field updates tagged to this zone.\n",
            encoding="utf-8",
        )
        created.append(
            {
                "id": z.id,
                "label": z.label,
                "polygon": spec["polygon"],
            }
        )
    db.commit()

    # stash raw file in wiki sources
    if source_name:
        src = root / "wiki" / "sources" / Path(source_name).name
        src.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (bytes, bytearray)):
            src.write_bytes(payload)
        elif isinstance(payload, str):
            src.write_text(payload, encoding="utf-8")
        else:
            src.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # link from index
    index = root / "wiki" / "index.md"
    if index.exists():
        text = index.read_text(encoding="utf-8")
        links = []
        for c in created:
            slug = re.sub(r"[^a-z0-9]+", "-", c["label"].lower()).strip("-") or "zone"
            links.append(f"- [[zones/{slug}]] — {c['label']}")
        block = "\n## Site map (imported)\n\n" + "\n".join(links) + "\n"
        if "## Site map (imported)" in text:
            parts = text.split("## Site map (imported)")
            rest = parts[1]
            nxt = rest.find("\n## ")
            text = (
                parts[0] + block + rest[nxt + 1 :]
                if nxt >= 0
                else parts[0] + block
            )
        else:
            text = text.rstrip() + "\n" + block
        index.write_text(text, encoding="utf-8")

    return {
        "project_id": project_id,
        "replaced": removed,
        "zones": created,
        "count": len(created),
        "source": source_name,
    }
