"""Folder-organized Karpathy-style wiki layout (no OpenKB).

Folder taxonomy is **not** hardcoded at project create. Supervisor `/init`
(or ingest paths) mkdir folders as needed; the API discovers whatever exists.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Hint for Hermes /init only — API does not pre-create these.
SUGGESTED_FOLDERS = (
    "zones",
    "people",
    "sources",
    "maps",
    "pos",
    "rfis",
    "ops",
    "media",
    "pageindex",
)

# Back-compat alias used by classify / resolve heuristics
FOLDERS = SUGGESTED_FOLDERS

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp"}
PDF_SUFFIXES = {".pdf"}
MAP_SUFFIXES = {".geojson", ".json"} | IMAGE_SUFFIXES | PDF_SUFFIXES

_OPS = {
    "log.md",
    "safety-log.md",
    "schedule-flags.md",
    "task-board.md",
    "white-space.md",
    "agents.md",
}

_SKIP_DIR_NAMES = {".git", "__pycache__", ".openkb"}


def ensure_wiki_layout(kb_root: Path) -> Path:
    """Minimal scaffold: raw/ + wiki/ + index.md. No folder taxonomy."""
    kb_root = Path(kb_root)
    (kb_root / "raw").mkdir(parents=True, exist_ok=True)
    wiki = kb_root / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    index = wiki / "index.md"
    if not index.exists():
        index.write_text(_empty_index(), encoding="utf-8")
    openkb = kb_root / ".openkb"
    if openkb.is_dir():
        shutil.rmtree(openkb, ignore_errors=True)
    return wiki


def discover_folders(wiki: Path) -> list[str]:
    """Return existing first-level wiki subdirs (sorted)."""
    wiki = Path(wiki)
    if not wiki.is_dir():
        return []
    out: list[str] = []
    for p in sorted(wiki.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_dir():
            continue
        if p.name in _SKIP_DIR_NAMES or p.name.startswith("."):
            continue
        out.append(p.name)
    return out


def ensure_folder(wiki: Path, folder: str) -> Path:
    """Create one wiki subfolder on demand (Hermes / init / ingest)."""
    name = folder.strip().strip("/")
    if not name or "/" in name or name.startswith(".") or name in _SKIP_DIR_NAMES:
        raise ValueError(f"invalid wiki folder: {folder!r}")
    d = Path(wiki) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def classify_page(name: str) -> str:
    """Return suggested folder for a wiki page filename (migration / compile)."""
    low = name.lower()
    if low in _OPS or low.startswith("ops-"):
        return "ops"
    if low.startswith(("source-", "sources/")):
        return "sources"
    if low.startswith(("po-", "pos/")):
        return "pos"
    if low.startswith(("rfi", "rfis/")):
        return "rfis"
    if low.startswith(("zone-", "zones/")):
        return "zones"
    if low.startswith(("map-", "maps/")) or "sitemap" in low or "site-plan" in low:
        return "maps"
    stem = Path(name).stem.lower()
    if "-" in stem and not stem.startswith(
        (
            "source-",
            "po-",
            "zone-",
            "rfi",
            "task-",
            "schedule-",
            "safety-",
            "white-",
            "map-",
        )
    ):
        parts = stem.split("-")
        if len(parts) >= 2 and all(p.isalpha() for p in parts[:2]):
            return "people"
    return "sources"


def migrate_flat_wiki(wiki: Path) -> list[str]:
    """Move loose wiki/*.md into folder buckets. Returns moved paths."""
    moved: list[str] = []
    for md in list(wiki.glob("*.md")):
        if md.name == "index.md":
            continue
        folder = classify_page(md.name)
        dest = wiki / folder / md.name
        if dest.resolve() == md.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            md.unlink(missing_ok=True)
            moved.append(f"removed-dup:{md.name}")
            continue
        shutil.move(str(md), str(dest))
        moved.append(f"{folder}/{md.name}")
    return moved


def rebuild_index(wiki: Path, *, project_id: str | None = None) -> Path:
    lines = [
        "# FieldClaw Wiki Index",
        "",
        "Folder-organized site knowledge base (markdown only — no OpenKB).",
        "",
    ]
    if project_id:
        lines.append(f"Project `{project_id}`")
        lines.append("")
    for folder in discover_folders(wiki):
        if folder == "pageindex":
            continue
        d = wiki / folder
        pages = sorted(d.glob("*.md")) if d.is_dir() else []
        if not pages:
            continue
        lines.append(f"## {folder}/")
        lines.append("")
        for md in pages:
            first = md.read_text(encoding="utf-8", errors="replace").splitlines()
            headline = first[0].lstrip("# ").strip() if first else md.stem
            lines.append(f"- [[{folder}/{md.stem}]] — {headline}")
        lines.append("")
    pi = wiki / "pageindex"
    if pi.is_dir():
        trees = sorted(pi.glob("*.json"))
        if trees:
            lines.append("## pageindex/ (large PDF trees)")
            lines.append("")
            for j in trees:
                lines.append(f"- `{j.name}` — PageIndex tree")
            lines.append("")
    index = wiki / "index.md"
    index.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return index


def list_wiki_pages(kb_root: Path) -> list[dict]:
    wiki = ensure_wiki_layout(kb_root)
    migrate_flat_wiki(wiki)
    pages: list[dict] = []
    index = wiki / "index.md"
    if index.exists():
        pages.append(
            {
                "path": "index.md",
                "folder": "",
                "title": "Index",
                "bytes": index.stat().st_size,
            }
        )
    for folder in discover_folders(wiki):
        d = wiki / folder
        for md in sorted(d.rglob("*.md")):
            rel = md.relative_to(wiki).as_posix()
            first = md.read_text(encoding="utf-8", errors="replace").splitlines()
            title = first[0].lstrip("# ").strip() if first else md.stem
            pages.append(
                {
                    "path": rel,
                    "folder": folder,
                    "title": f"{folder}/{title}" if folder else title,
                    "bytes": md.stat().st_size,
                }
            )
        if folder == "pageindex":
            for j in sorted(d.glob("*.json")):
                rel = j.relative_to(wiki).as_posix()
                pages.append(
                    {
                        "path": rel,
                        "folder": folder,
                        "title": f"pageindex/{j.stem}",
                        "bytes": j.stat().st_size,
                    }
                )
    return pages


def list_wiki_assets(kb_root: Path) -> list[dict]:
    """List renderable binaries: PDFs, images, GeoJSON under wiki/ (+ raw PDFs)."""
    kb_root = Path(kb_root)
    wiki = ensure_wiki_layout(kb_root)
    raw = kb_root / "raw"
    assets: list[dict] = []
    seen: set[str] = set()

    def add(path: Path, *, root: Path, kind: str, folder: str) -> None:
        if not path.is_file():
            return
        rel = path.relative_to(root).as_posix()
        key = f"{kind}:{rel}"
        if key in seen:
            return
        seen.add(key)
        suf = path.suffix.lower()
        atype = (
            "pdf"
            if suf in PDF_SUFFIXES
            else "image"
            if suf in IMAGE_SUFFIXES
            else "geojson"
            if suf in (".geojson",)
            or (suf == ".json" and "sitemap" in path.name.lower())
            else "file"
        )
        if atype == "file":
            return
        assets.append(
            {
                "path": rel,
                "root": "wiki" if root == wiki else "raw",
                "folder": folder,
                "name": path.name,
                "type": atype,
                "bytes": path.stat().st_size,
                "kind": kind,
            }
        )

    for folder in discover_folders(wiki):
        d = wiki / folder
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            suf = p.suffix.lower()
            if suf not in MAP_SUFFIXES and suf not in PDF_SUFFIXES:
                continue
            if suf == ".json" and not (
                p.name.lower().endswith(".geojson")
                or "sitemap" in p.name.lower()
                or "geojson" in p.name.lower()
                or folder == "maps"
            ):
                continue
            add(p, root=wiki, kind="wiki", folder=folder)

    for p in sorted(wiki.glob("*.geojson")):
        add(p, root=wiki, kind="wiki", folder="")

    if raw.is_dir():
        for p in sorted(raw.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() in PDF_SUFFIXES | IMAGE_SUFFIXES:
                add(p, root=raw, kind="raw", folder="raw")
            if p.suffix.lower() == ".geojson" or (
                p.suffix.lower() == ".json" and "sitemap" in p.name.lower()
            ):
                add(p, root=raw, kind="raw", folder="raw")

    by_name: dict[str, dict] = {}
    ordered: list[dict] = []
    for a in assets:
        if a["root"] == "wiki":
            by_name[a["name"]] = a
            ordered.append(a)
    for a in assets:
        if a["root"] == "raw" and a["name"] not in by_name:
            ordered.append(a)
    return ordered


def resolve_wiki_path(wiki: Path, path: str) -> Path:
    """Resolve a relative wiki path; blocks path traversal."""
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise FileNotFoundError(path)
    if not rel.suffix:
        for suf in (".md", ".json", *sorted(IMAGE_SUFFIXES)):
            cand = (wiki / f"{rel}{suf}").resolve()
            if cand.exists() and str(cand).startswith(str(wiki.resolve())):
                return cand
        name = rel.name + ".md"
        for folder in ("", *discover_folders(wiki)):
            cand = wiki / folder / name if folder else wiki / name
            if cand.exists():
                return cand.resolve()
        raise FileNotFoundError(path)
    target = (wiki / rel).resolve()
    if not str(target).startswith(str(wiki.resolve())):
        raise FileNotFoundError(path)
    if not target.exists():
        if len(rel.parts) == 1:
            folder = classify_page(rel.name)
            alt = wiki / folder / rel.name
            if alt.exists():
                return alt.resolve()
            media_alt = wiki / "media" / rel.name
            if media_alt.exists():
                return media_alt.resolve()
        raise FileNotFoundError(path)
    return target


def _empty_index() -> str:
    return (
        "# FieldClaw Wiki Index\n\n"
        "Site knowledge base. Folders are created by Supervisor `/init` "
        "(or as mail/docs arrive) — the API does not hardcode the taxonomy.\n\n"
    )


def append_ops_log(wiki: Path, line: str) -> Path:
    ensure_wiki_layout(wiki.parent if wiki.name == "wiki" else wiki)
    if wiki.name != "wiki":
        wiki = ensure_wiki_layout(wiki)
    ensure_folder(wiki, "ops")
    log = wiki / "ops" / "log.md"
    if not log.exists():
        log.write_text("# Site log\n\n", encoding="utf-8")
    with log.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")
    return log
