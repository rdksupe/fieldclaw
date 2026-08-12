import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.models import Project
from fieldclaw_api.schemas import EventCreate
from fieldclaw_api.services import datalab_svc, pageindex_svc, wiki_layout
from fieldclaw_api.services.logbook import append_event

IMAGE_SUFFIXES = wiki_layout.IMAGE_SUFFIXES


def _project_kb(db: Session, project_id: str) -> Path:
    project = db.get(Project, project_id)
    if not project:
        raise FileNotFoundError("project not found")
    rel = project.kb_relpath or f"projects/{project_id}"
    root = settings.fieldclaw_kb_dir / rel
    wiki_layout.ensure_wiki_layout(root)
    return root


def _raw_dir(db: Session, project_id: str) -> Path:
    return _project_kb(db, project_id) / "raw"


def _wiki_dir(db: Session, project_id: str) -> Path:
    return _project_kb(db, project_id) / "wiki"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "doc"


def pdf_to_markdown(pdf_path: Path) -> tuple[str, str]:
    """Default: Datalab. Returns (markdown, engine)."""
    return datalab_svc.pdf_to_markdown(pdf_path)


def _write_entity(wiki: Path, folder: str, name: str, body: str) -> Path:
    dest = wiki / folder / f"{_slug(name)}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and folder in ("zones", "people"):
        # append mention rather than overwrite
        existing = dest.read_text(encoding="utf-8")
        if body.strip() not in existing:
            dest.write_text(
                existing.rstrip() + "\n\n" + body.strip() + "\n", encoding="utf-8"
            )
        return dest
    dest.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
    return dest


def compile_wiki_from_raw(db: Session, project_id: str, raw_path: Path) -> list[Path]:
    text = raw_path.read_text(encoding="utf-8")
    title = raw_path.stem
    pos = sorted(set(re.findall(r"PO-\d{4,6}", text, flags=re.IGNORECASE)))
    zones = sorted(set(re.findall(r"Zone\s+[A-Z0-9]+", text, flags=re.IGNORECASE)))
    rfis = sorted(set(re.findall(r"RFI[-\s]?\d*", text, flags=re.IGNORECASE)))

    wiki = _wiki_dir(db, project_id)
    page_path = wiki / "sources" / f"source-{_slug(title)}.md"
    summary_lines = [
        f"# {title}",
        "",
        f"Source: `raw/{raw_path.name}`",
        "",
        "## Summary",
        "",
        text[:1200].strip() + ("…" if len(text) > 1200 else ""),
        "",
        "## Entities",
        "",
    ]
    for po in pos:
        summary_lines.append(f"- [[pos/{_slug(po)}]] ({po})")
    for z in zones:
        summary_lines.append(f"- [[zones/{_slug(z)}]] ({z})")
    for r in rfis:
        summary_lines.append(f"- [[rfis/{_slug(r)}]] ({r})")
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    written = [page_path]
    for po in pos:
        written.append(
            _write_entity(
                wiki,
                "pos",
                po,
                f"# {po}\n\nMentioned in [[sources/{page_path.stem}]].\n\nRaw: `raw/{raw_path.name}`\n",
            )
        )
    for z in zones:
        written.append(
            _write_entity(
                wiki,
                "zones",
                z,
                f"# {z}\n\nMentioned in [[sources/{page_path.stem}]].\n",
            )
        )
    for r in rfis:
        written.append(
            _write_entity(
                wiki,
                "rfis",
                r,
                f"# {r}\n\nMentioned in [[sources/{page_path.stem}]].\n",
            )
        )

    wiki_layout.rebuild_index(wiki, project_id=project_id)
    written.append(wiki / "index.md")
    return written


def ingest_image(
    db: Session,
    project_id: str,
    filename: str,
    data: bytes,
    *,
    caption: str | None = None,
    event_id: str | None = None,
    zone_id: str | None = None,
    content_type: str | None = None,
) -> dict:
    """Save a site photo into raw/media + wiki/media and link it from ops/log."""
    kb_root = _project_kb(db, project_id)
    wiki = kb_root / "wiki"
    media_raw = kb_root / "raw" / "media"
    media_wiki = wiki / "media"
    media_raw.mkdir(parents=True, exist_ok=True)
    media_wiki.mkdir(parents=True, exist_ok=True)

    suffix = Path(filename).suffix.lower() or ".jpg"
    if suffix not in IMAGE_SUFFIXES:
        # trust content-type hint
        if content_type and "png" in content_type:
            suffix = ".png"
        elif content_type and "webp" in content_type:
            suffix = ".webp"
        else:
            suffix = ".jpg"
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    stem = _slug(Path(filename).stem) or "photo"
    safe = f"{ts}-{stem}{suffix}"
    bin_path = media_raw / safe
    bin_path.write_bytes(data)
    # copy into wiki/media so relative markdown links work
    wiki_bin = media_wiki / safe
    shutil.copy2(bin_path, wiki_bin)

    title = caption.strip() if caption and caption.strip() else stem.replace("-", " ")
    page = media_wiki / f"{Path(safe).stem}.md"
    lines = [
        f"# {title}",
        "",
        f"![{title}]({safe})",
        "",
        f"- File: `wiki/media/{safe}`",
        f"- Raw: `raw/media/{safe}`",
        f"- Uploaded: `{datetime.now(UTC).isoformat()}`",
    ]
    if event_id:
        lines.append(f"- Event: `{event_id}`")
    if zone_id:
        lines.append(f"- Zone: `{zone_id}`")
    if content_type:
        lines.append(f"- Content-Type: `{content_type}`")
    lines.append("")
    page.write_text("\n".join(lines), encoding="utf-8")

    rel_root = (
        db.get(Project, project_id).kb_relpath if db.get(Project, project_id) else None
    ) or f"projects/{project_id}"
    log_line = (
        f"- `{datetime.now(UTC).isoformat()}` **photo** — {title} "
        f"→ [[media/{page.stem}]] ![](../media/{safe})"
    )
    wiki_layout.append_ops_log(wiki, log_line)
    if zone_id:
        from fieldclaw_api.models import Zone

        zone = db.get(Zone, zone_id)
        label = zone.label if zone else zone_id
        zpath = wiki / "zones" / f"{_slug(label)}.md"
        if not zpath.exists():
            zpath.write_text(f"# {label}\n\n## Field updates\n\n", encoding="utf-8")
        with zpath.open("a", encoding="utf-8") as f:
            f.write(f"- photo: [[{page.stem}]] — {title} ![](../media/{safe})\n")

    wiki_layout.rebuild_index(wiki, project_id=project_id)
    outs = append_event(
        db,
        project_id,
        EventCreate(
            type="wiki.updated",
            source="media",
            zone_id=zone_id,
            payload={
                "engine": "image",
                "caption": title,
                "event_id": event_id,
                "raw": f"{rel_root}/raw/media/{safe}",
                "wiki_page": f"media/{page.name}",
                "wiki_file": f"media/{safe}",
                "pages": [f"media/{page.name}", f"media/{safe}"],
            },
            proof_ids=[],
        ),
    )
    return {
        "raw": f"media/{safe}",
        "wiki_page": f"media/{page.name}",
        "wiki_file": f"media/{safe}",
        "caption": title,
        "kb_relpath": rel_root,
        "engine": "image",
        "events": [e.model_dump(mode="json") for e in outs],
    }


def ingest_bytes(
    db: Session,
    project_id: str,
    filename: str,
    data: bytes,
    content_type: str | None,
    *,
    caption: str | None = None,
    event_id: str | None = None,
    zone_id: str | None = None,
) -> dict:
    suffix = Path(filename).suffix.lower()
    is_image = suffix in IMAGE_SUFFIXES or ((content_type or "").startswith("image/"))
    if is_image:
        return ingest_image(
            db,
            project_id,
            filename,
            data,
            caption=caption,
            event_id=event_id,
            zone_id=zone_id,
            content_type=content_type,
        )

    raw = _raw_dir(db, project_id)
    safe = _slug(Path(filename).stem) + Path(filename).suffix.lower()
    dest = raw / safe
    dest.write_bytes(data)

    project = db.get(Project, project_id)
    rel_root = project.kb_relpath if project else f"projects/{project_id}"
    kb_root = _project_kb(db, project_id)
    wiki = kb_root / "wiki"
    # Mirror binaries into wiki so the web UI can render PDFs/images (not only markdown stubs).
    try:
        from fieldclaw_api.services.sitemap import is_sitemap_filename

        wiki_layout.ensure_wiki_layout(kb_root)
        if dest.suffix.lower() in {".pdf", *IMAGE_SUFFIXES}:
            src_dest = wiki / "sources" / dest.name
            src_dest.write_bytes(data)
            if is_sitemap_filename(filename) or is_sitemap_filename(dest.name):
                maps_dest = wiki / "maps" / dest.name
                maps_dest.write_bytes(data)
    except Exception:
        pass
    engine = "datalab"
    pageindex_meta: dict | None = None
    extract_engine = "datalab"

    if dest.suffix.lower() == ".pdf" and pageindex_svc.should_use_pageindex(dest):
        tree_path = wiki / "pageindex" / f"{dest.stem}.json"
        pageindex_meta = pageindex_svc.run_pageindex(dest, tree_path, flash=True)
        # Full-text extract always via Datalab (pypdf only as emergency fallback)
        md_text, extract_engine = pdf_to_markdown(dest)
        md_path = raw / f"{dest.stem}.md"
        md_path.write_text(md_text, encoding="utf-8")
        if pageindex_meta.get("ok") and tree_path.exists():
            outline = pageindex_svc.tree_summary_markdown(
                tree_path, title=dest.stem, raw_name=dest.name
            )
            src_page = wiki / "sources" / f"source-{_slug(dest.stem)}.md"
            src_page.write_text(outline, encoding="utf-8")
            written = compile_wiki_from_raw(db, project_id, md_path)
            # restore richer outline page
            src_page.write_text(outline, encoding="utf-8")
            wiki_layout.rebuild_index(wiki, project_id=project_id)
            engine = f"pageindex+{extract_engine}"
            pages = [str(p.relative_to(wiki)) for p in written if p.exists()]
            pages.append(f"pageindex/{tree_path.name}")
            outs = append_event(
                db,
                project_id,
                EventCreate(
                    type="wiki.updated",
                    source="pageindex",
                    payload={
                        "engine": engine,
                        "extract": extract_engine,
                        "raw": f"{rel_root}/raw/{dest.name}",
                        "pages": pages[:40],
                        "pageindex": {
                            "ok": True,
                            "tree": f"wiki/pageindex/{tree_path.name}",
                        },
                    },
                ),
            )
            return {
                "raw": dest.name,
                "pages": pages,
                "kb_relpath": rel_root,
                "engine": engine,
                "events": [e.model_dump(mode="json") for e in outs],
            }

    if dest.suffix.lower() == ".pdf":
        md_path = raw / f"{dest.stem}.md"
        md_text, extract_engine = pdf_to_markdown(dest)
        md_path.write_text(md_text, encoding="utf-8")
        compile_from = md_path
        engine = extract_engine
    elif dest.suffix.lower() in (".md", ".txt"):
        compile_from = dest
        engine = "markdown"
    else:
        md_path = raw / f"{dest.stem}.md"
        md_path.write_text(
            f"# {filename}\n\nBinary/other file stored at `raw/{dest.name}`.\n",
            encoding="utf-8",
        )
        compile_from = md_path
        engine = "binary-stub"

    written = compile_wiki_from_raw(db, project_id, compile_from)
    pages = [
        str(p.relative_to(wiki)) if p.is_relative_to(wiki) else p.name for p in written
    ]
    outs = append_event(
        db,
        project_id,
        EventCreate(
            type="wiki.updated",
            source="wiki",
            payload={
                "engine": engine,
                "raw": f"{rel_root}/raw/{compile_from.name}",
                "pages": pages,
                "pageindex_attempt": pageindex_meta,
            },
        ),
    )
    return {
        "raw": compile_from.name,
        "pages": pages,
        "kb_relpath": rel_root,
        "engine": engine,
        "events": [e.model_dump(mode="json") for e in outs],
    }


def read_index(db: Session, project_id: str) -> str:
    wiki = _wiki_dir(db, project_id)
    wiki_layout.migrate_flat_wiki(wiki)
    path = wiki_layout.rebuild_index(wiki, project_id=project_id)
    return path.read_text(encoding="utf-8")


def read_page(db: Session, project_id: str, path: str) -> str:
    wiki = _wiki_dir(db, project_id)
    target = wiki_layout.resolve_wiki_path(wiki, path)
    if target.suffix == ".json":
        return (
            f"# {target.stem} (PageIndex tree)\n\n"
            f"```json\n{target.read_text(encoding='utf-8')[:12000]}\n```\n"
        )
    return target.read_text(encoding="utf-8")


def lookup(db: Session, project_id: str, query: str) -> dict:
    index = read_index(db, project_id)
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9\-]{2,}", query)]
    wiki = _wiki_dir(db, project_id)
    scored: list[tuple[int, Path]] = []
    for md in wiki.rglob("*.md"):
        body = md.read_text(encoding="utf-8")
        low = body.lower()
        score = sum(low.count(t) for t in terms)
        if md.name == "index.md":
            score += sum(index.lower().count(t) for t in terms)
        if score:
            scored.append((score, md))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    top = scored[:5]
    citations = []
    snippets = []
    for score, md in top:
        text = md.read_text(encoding="utf-8")
        rel = md.relative_to(wiki).as_posix()
        citations.append({"path": f"wiki/{rel}", "score": score})
        snippets.append(f"### {rel}\n\n{text[:800]}")
    answer = "Based on the folder wiki (no vector DB):\n\n" + (
        "\n\n".join(snippets) if snippets else "No matching wiki pages."
    )
    return {"query": query, "answer": answer, "citations": citations}


def ingest_inbox_attachments(db: Session, project_id: str) -> dict:
    from fieldclaw_api.services import agentmail_svc
    from fieldclaw_api.services import sitemap as sitemap_svc

    project = db.get(Project, project_id)
    if not project or not project.inbox_email:
        raise RuntimeError("project has no inbox_email")
    raw = _raw_dir(db, project_id)
    saved = agentmail_svc.pull_attachments_into_dir(project.inbox_email, raw)
    ingested = []
    sitemaps = []
    for item in saved:
        data = Path(item["path"]).read_bytes()
        fname = item["filename"]
        low = fname.lower()
        if low.endswith(".geojson") or (
            low.endswith(".json") and sitemap_svc.is_sitemap_filename(fname)
        ):
            try:
                sitemaps.append(
                    sitemap_svc.import_geojson(
                        db,
                        project_id,
                        data,
                        replace=True,
                        source_name=fname,
                    )
                )
                continue
            except Exception as e:
                sitemaps.append({"filename": fname, "error": str(e)})
                continue
        if sitemap_svc.is_sitemap_filename(fname) and low.endswith(
            (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
        ):
            try:
                sitemaps.append(
                    sitemap_svc.import_from_document(
                        db,
                        project_id,
                        data,
                        filename=fname,
                        replace=True,
                    )
                )
                continue
            except Exception as e:
                sitemaps.append({"filename": fname, "error": str(e)})
                # fall through to normal ingest so the PDF still lands in wiki
        ingested.append(ingest_bytes(db, project_id, fname, data, "application/pdf"))
    return {"saved": saved, "ingested": ingested, "sitemaps": sitemaps}


def mirror_event_to_wiki(
    db: Session,
    project_id: str,
    *,
    event_type: str,
    payload: dict,
    zone_id: str | None = None,
    actor_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Append field/status reports into wiki/ops/log.md (+ zone page)."""
    wiki = _wiki_dir(db, project_id)
    ts = created_at or ""
    summary = (
        payload.get("summary")
        or payload.get("message")
        or payload.get("material")
        or payload.get("text")
        or payload.get("reason")
        or str(payload)[:200]
    )
    line = f"- `{ts}` **{event_type}** — {summary}"
    media = payload.get("wiki_file") or payload.get("media") or payload.get("path")
    if media and str(media).lower().endswith(tuple(IMAGE_SUFFIXES)):
        # normalize to wiki/media relative name when possible
        name = Path(str(media)).name
        line += (
            f"  ![](../media/{name})"
            if not str(media).startswith("http")
            else f"  ![]({media})"
        )
    elif payload.get("wiki_page"):
        line += f" → [[{payload['wiki_page'].replace('.md', '')}]]"
    if zone_id:
        line += f" _(zone `{zone_id[:8]}…`)_"
    if actor_id:
        line += f" _(actor `{actor_id[:8]}…`)_"
    wiki_layout.append_ops_log(wiki, line)

    if zone_id:
        from fieldclaw_api.models import Zone

        zone = db.get(Zone, zone_id)
        label = zone.label if zone else zone_id
        zpath = wiki / "zones" / f"{_slug(label)}.md"
        if not zpath.exists():
            zpath.write_text(f"# {label}\n\n## Field updates\n\n", encoding="utf-8")
        with zpath.open("a", encoding="utf-8") as f:
            f.write(f"- `{ts}` **{event_type}** — {summary}\n")
    wiki_layout.rebuild_index(wiki, project_id=project_id)
