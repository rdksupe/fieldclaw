#!/usr/bin/env python3
"""Hermes-facing wiki helpers — ingest/index only.

PDF → markdown defaults to **Datalab** (pypdf only if DATALAB_API_KEY missing/fails).
Large PDFs also get a PageIndex structure tree.

For lookup/Q&A: use normal filesystem tools (`ls`, `rg`, `cat` / `read_file`) on
`kb/projects/{id}/wiki/` — do not rely on `wiki_fs.py lookup`.

Usage:
  python wiki_fs.py index
  python wiki_fs.py read zones/zone-a.md
  python wiki_fs.py ingest path/to/file.pdf          # Datalab default
  python wiki_fs.py pageindex path/to/large.pdf      # PageIndex tree + Datalab MD
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KB = ROOT / "kb"
DATALAB_CONVERT_URL = "https://www.datalab.to/api/v1/convert"
SCRIPTS = Path(__file__).resolve().parent / "scripts"
# Suggested taxonomy for `/init` — do NOT auto-create on every call.
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
FOLDERS = SUGGESTED_FOLDERS  # back-compat


def kb_dir() -> Path:
    """Prefer project-isolated KB root: kb/projects/{id}."""
    explicit = os.environ.get("FIELDCLAW_KB_DIR")
    if explicit:
        p = Path(explicit).resolve()
        p.mkdir(parents=True, exist_ok=True)
        (p / "wiki").mkdir(parents=True, exist_ok=True)
        (p / "raw").mkdir(parents=True, exist_ok=True)
        return p
    try:
        sys.path.insert(0, str(SCRIPTS))
        from resolve_project import kb_root, resolve  # type: ignore

        return Path(kb_root(resolve()))
    except SystemExit:
        # resolve_project exits when API has no projects — fall back for local tools
        return DEFAULT_KB.resolve()
    except Exception:
        return DEFAULT_KB.resolve()


def discover_folders(wiki: Path) -> list[str]:
    if not wiki.is_dir():
        return []
    skip = {".git", "__pycache__", ".openkb"}
    return sorted(
        p.name
        for p in wiki.iterdir()
        if p.is_dir() and p.name not in skip and not p.name.startswith(".")
    )


def ensure_layout() -> Path:
    """Minimal scaffold only — folders come from `/init` or on-demand writes."""
    root = kb_dir()
    (root / "raw").mkdir(parents=True, exist_ok=True)
    wiki = root / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    index = wiki / "index.md"
    if not index.exists():
        index.write_text(
            "# FieldClaw Wiki Index\n\n"
            "Folders are created by Supervisor `/init` (or as docs arrive).\n\n",
            encoding="utf-8",
        )
    # migrate flat files into suggested buckets (mkdir those only)
    for md in list(wiki.glob("*.md")):
        if md.name == "index.md":
            continue
        folder = _classify(md.name)
        dest = wiki / folder / md.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.move(str(md), str(dest))
    openkb = root / ".openkb"
    if openkb.is_dir():
        shutil.rmtree(openkb, ignore_errors=True)
    return wiki


def scaffold_suggested(wiki: Path | None = None) -> list[str]:
    """Create suggested folder set + ops/log stub. Used by `/init`."""
    wiki = wiki or ensure_layout()
    created: list[str] = []
    for name in SUGGESTED_FOLDERS:
        d = wiki / name
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(name)
        else:
            d.mkdir(parents=True, exist_ok=True)
    log = wiki / "ops" / "log.md"
    if not log.exists():
        log.write_text(
            "# Site log\n\nStatus and field reports land here automatically.\n\n",
            encoding="utf-8",
        )
        created.append("ops/log.md")
    agents = wiki / "ops" / "agents.md"
    if not agents.exists():
        agents.write_text(
            "# Agents\n\nSupervisor Claw + Foreman profiles. Update after pairing.\n\n",
            encoding="utf-8",
        )
    rebuild_index(wiki)
    return created
    """Prefer project-isolated KB root: kb/projects/{id}."""
    explicit = os.environ.get("FIELDCLAW_KB_DIR")
    if explicit:
        p = Path(explicit).resolve()
        if (p / "wiki").is_dir():
            return p
        try:
            sys.path.insert(0, str(SCRIPTS))
            from resolve_project import kb_root, resolve  # type: ignore

            return Path(kb_root(resolve()))
        except Exception:
            return p
    try:
        sys.path.insert(0, str(SCRIPTS))
        from resolve_project import kb_root, resolve  # type: ignore

        return Path(kb_root(resolve()))
    except Exception:
        return DEFAULT_KB.resolve()


def ensure_layout() -> Path:
    root = kb_dir()
    (root / "raw").mkdir(parents=True, exist_ok=True)
    wiki = root / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    for name in FOLDERS:
        (wiki / name).mkdir(parents=True, exist_ok=True)
    # migrate flat files
    for md in list(wiki.glob("*.md")):
        if md.name == "index.md":
            continue
        folder = _classify(md.name)
        dest = wiki / folder / md.name
        if not dest.exists():
            shutil.move(str(md), str(dest))
    openkb = root / ".openkb"
    if openkb.is_dir():
        shutil.rmtree(openkb, ignore_errors=True)
    return wiki


def raw_dir() -> Path:
    p = kb_dir() / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def wiki_dir() -> Path:
    return ensure_layout()


def slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "doc"


def _classify(name: str) -> str:
    low = name.lower()
    if low in {
        "log.md",
        "safety-log.md",
        "schedule-flags.md",
        "task-board.md",
        "white-space.md",
    }:
        return "ops"
    if low.startswith("source-"):
        return "sources"
    if low.startswith("po-"):
        return "pos"
    if low.startswith("rfi"):
        return "rfis"
    if low.startswith("zone-"):
        return "zones"
    stem = Path(name).stem.lower()
    parts = stem.split("-")
    if len(parts) >= 2 and all(p.isalpha() for p in parts[:2]):
        return "people"
    return "sources"


def _pypdf_fallback(pdf_path: Path, note: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    parts = [f"# {pdf_path.stem}\n", f"\n<!-- {note} -->\n"]
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"\n## Page {i}\n\n{text.strip()}\n")
    return "\n".join(parts)


def datalab_to_markdown(doc_path: Path, *, mode: str | None = None) -> str:
    import requests

    api_key = os.environ.get("DATALAB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DATALAB_API_KEY not set (Hermes .env)")

    mode = mode or os.environ.get("DATALAB_MODE", "balanced")
    headers = {"X-API-Key": api_key}
    with doc_path.open("rb") as f:
        resp = requests.post(
            DATALAB_CONVERT_URL,
            headers=headers,
            files={"file": (doc_path.name, f)},
            data={
                "output_format": "markdown",
                "mode": mode,
                "paginate": "true",
                "token_efficient_markdown": "true",
            },
            timeout=120,
        )
    resp.raise_for_status()
    body = resp.json()
    check_url = body.get("request_check_url")
    if not check_url:
        raise RuntimeError(f"datalab: no request_check_url in {body}")

    for _ in range(300):
        result = requests.get(check_url, headers=headers, timeout=60).json()
        status = result.get("status")
        if status == "complete":
            if not result.get("success", True):
                raise RuntimeError(f"datalab failed: {result.get('error')}")
            md = result.get("markdown") or ""
            return f"# {doc_path.stem}\n\n{md.strip()}\n"
        if status == "failed":
            raise RuntimeError(f"datalab failed: {result.get('error')}")
        time.sleep(2)
    raise TimeoutError("datalab convert timed out")


def pdf_to_markdown(pdf_path: Path) -> tuple[str, str]:
    """Default extract: Datalab. Returns (markdown, engine)."""
    if not os.environ.get("DATALAB_API_KEY", "").strip():
        return _pypdf_fallback(pdf_path, "DATALAB_API_KEY missing — pypdf fallback"), "pypdf"
    try:
        return datalab_to_markdown(pdf_path), "datalab"
    except Exception as e:
        return _pypdf_fallback(pdf_path, f"datalab failed: {e} — pypdf fallback"), "pypdf"


def rebuild_index(wiki: Path) -> None:
    lines = [
        "# FieldClaw Wiki Index",
        "",
        "Folder-organized site knowledge base.",
        "",
    ]
    for folder in discover_folders(wiki):
        if folder == "pageindex":
            continue
        pages = sorted((wiki / folder).glob("*.md")) if (wiki / folder).is_dir() else []
        if not pages:
            continue
        lines.append(f"## {folder}/")
        lines.append("")
        for md in pages:
            first = md.read_text(encoding="utf-8", errors="replace").splitlines()
            headline = first[0].lstrip("# ").strip() if first else md.stem
            lines.append(f"- [[{folder}/{md.stem}]] — {headline}")
        lines.append("")
    (wiki / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def compile_wiki_from_raw(raw_path: Path) -> list[Path]:
    text = raw_path.read_text(encoding="utf-8")
    title = raw_path.stem
    pos = sorted(set(re.findall(r"PO-\d{4,6}", text, flags=re.I)))
    zones = sorted(set(re.findall(r"Zone\s+[A-Z0-9]+", text, flags=re.I)))

    wiki = wiki_dir()
    (wiki / "sources").mkdir(parents=True, exist_ok=True)
    page_path = wiki / "sources" / f"source-{slug(title)}.md"
    lines = [
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
        lines.append(f"- [[pos/{slug(po)}]] ({po})")
    for z in zones:
        lines.append(f"- [[zones/{slug(z)}]] ({z})")
    page_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written = [page_path]

    for po in pos:
        (wiki / "pos").mkdir(parents=True, exist_ok=True)
        ep = wiki / "pos" / f"{slug(po)}.md"
        ep.write_text(
            f"# {po}\n\nMentioned in [[sources/{page_path.stem}]].\n\nRaw: `raw/{raw_path.name}`\n",
            encoding="utf-8",
        )
        written.append(ep)
    for z in zones:
        (wiki / "zones").mkdir(parents=True, exist_ok=True)
        ep = wiki / "zones" / f"{slug(z)}.md"
        if not ep.exists():
            ep.write_text(
                f"# {z}\n\nMentioned in [[sources/{page_path.stem}]].\n",
                encoding="utf-8",
            )
            written.append(ep)

    rebuild_index(wiki)
    return written


def _store_and_compile(src: Path, markdown: str | None) -> list[Path]:
    dest = raw_dir() / src.name
    dest.write_bytes(src.read_bytes())
    engine = "markdown"
    if markdown is not None:
        md_path = raw_dir() / f"{dest.stem}.md"
        md_path.write_text(markdown, encoding="utf-8")
        compile_from = md_path
        engine = "datalab" if "datalab" in (markdown[:200].lower() + "") else "provided"
    elif dest.suffix.lower() == ".pdf":
        md_path = raw_dir() / f"{dest.stem}.md"
        md_text, engine = pdf_to_markdown(dest)
        md_path.write_text(md_text, encoding="utf-8")
        compile_from = md_path
        print(f"extract_engine={engine}", file=sys.stderr)
    elif dest.suffix.lower() in (".md", ".txt"):
        compile_from = dest
    else:
        md_path = raw_dir() / f"{dest.stem}.md"
        md_path.write_text(
            f"# {src.name}\n\nStored at `raw/{dest.name}`.\n", encoding="utf-8"
        )
        compile_from = md_path
    return compile_wiki_from_raw(compile_from)


def cmd_index(_: argparse.Namespace) -> int:
    wiki = wiki_dir()
    rebuild_index(wiki)
    sys.stdout.write((wiki / "index.md").read_text(encoding="utf-8"))
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    wiki = wiki_dir()
    rel = Path(args.path)
    target = wiki / rel
    if not target.exists() and not rel.suffix:
        target = wiki / f"{rel}.md"
    if not target.exists():
        # search folders
        name = rel.name if rel.suffix else f"{rel.name}.md"
        for folder in discover_folders(wiki):
            cand = wiki / folder / name
            if cand.exists():
                target = cand
                break
    if not target.exists():
        print(f"not found: {args.path}", file=sys.stderr)
        return 1
    sys.stdout.write(target.read_text(encoding="utf-8"))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """PDF/doc ingest — Datalab markdown by default."""
    src = Path(args.file).resolve()
    if not src.exists():
        print(f"missing file: {src}", file=sys.stderr)
        return 1
    written = _store_and_compile(src, markdown=None)
    print(f"compiled from {src.name} (datalab-default)")
    wiki = wiki_dir()
    for p in written:
        print(f"  wiki/{p.relative_to(wiki)}")
    return 0


def cmd_pageindex(args: argparse.Namespace) -> int:
    """Large PDF → PageIndex tree JSON + Datalab markdown extract + sources outline."""
    src = Path(args.file).resolve()
    if not src.exists():
        print(f"missing file: {src}", file=sys.stderr)
        return 1
    dest = raw_dir() / src.name
    dest.write_bytes(src.read_bytes())
    md_text, extract_engine = pdf_to_markdown(dest)
    md_path = raw_dir() / f"{dest.stem}.md"
    md_path.write_text(md_text, encoding="utf-8")
    written = compile_wiki_from_raw(md_path)

    wiki = wiki_dir()
    (wiki / "pageindex").mkdir(parents=True, exist_ok=True)
    (wiki / "sources").mkdir(parents=True, exist_ok=True)
    out = wiki / "pageindex" / f"{dest.stem}.json"
    pi_root = Path(os.environ.get("PAGEINDEX_ROOT", "/home/rdksupe/building_shit/PageIndex"))
    script = pi_root / "run_pageindex.py"
    if not script.exists():
        print(f"PageIndex missing at {pi_root}", file=sys.stderr)
        print(f"extract_engine={extract_engine}; wiki pages written without tree", file=sys.stderr)
        for p in written:
            print(f"  wiki/{p.relative_to(wiki)}")
        return 1
    cmd = [sys.executable, str(script), "--pdf_path", str(dest), "--flash", "--no-summary"]
    proc = __import__("subprocess").run(
        cmd, cwd=str(out.parent), capture_output=True, text=True, timeout=900
    )
    found = None
    for cand in sorted(out.parent.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if dest.stem.lower() in cand.stem.lower() or cand == out:
            found = cand
            break
    if found and found != out:
        shutil.copy2(found, out)
        found = out
    if not found or not found.exists():
        print(proc.stderr or proc.stdout or "pageindex failed", file=sys.stderr)
        print(f"extract_engine={extract_engine}; markdown wiki still written", file=sys.stderr)
        return 1
    outline = [
        f"# {dest.stem}",
        "",
        f"Source: `raw/{dest.name}`",
        f"Extract: `{extract_engine}` → `raw/{md_path.name}`",
        f"PageIndex: `wiki/pageindex/{out.name}`",
        "",
        "```json",
        found.read_text(encoding="utf-8")[:4000],
        "```",
        "",
    ]
    src_page = wiki / "sources" / f"source-{slug(dest.stem)}.md"
    src_page.write_text("\n".join(outline), encoding="utf-8")
    rebuild_index(wiki)
    print(f"pageindex → wiki/pageindex/{out.name}")
    print(f"extract_engine={extract_engine}")
    print(f"outline → wiki/sources/{src_page.name}")
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    """Create suggested wiki folders for /init (does not invent site facts)."""
    wiki = ensure_layout()
    created = scaffold_suggested(wiki)
    print(f"wiki={wiki}")
    print(f"created={','.join(created) if created else '(already present)'}")
    print(f"folders={','.join(discover_folders(wiki))}")
    return 0


def cmd_datalab_ingest(args: argparse.Namespace) -> int:
    """Alias of ingest (kept for older skill prompts)."""
    return cmd_ingest(args)


def cmd_lookup(args: argparse.Namespace) -> int:
    print(
        "wiki_fs lookup is deprecated. Use filesystem tools on the project wiki, e.g.:\n"
        f"  rg -n {args.query!r} kb/projects/<id>/wiki\n"
        "  ls wiki/ && cat wiki/index.md\n"
        "  cat wiki/sources/source-….md  wiki/pageindex/….json",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    p = argparse.ArgumentParser(description="FieldClaw wiki FS tools for Hermes")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index").set_defaults(func=cmd_index)

    sc = sub.add_parser("scaffold", help="Create suggested wiki folders (/init)")
    sc.set_defaults(func=cmd_scaffold)

    r = sub.add_parser("read")
    r.add_argument("path")
    r.set_defaults(func=cmd_read)

    i = sub.add_parser("ingest")
    i.add_argument("file")
    i.set_defaults(func=cmd_ingest)

    pi = sub.add_parser("pageindex", help="Large PDF → PageIndex tree")
    pi.add_argument("file")
    pi.set_defaults(func=cmd_pageindex)

    d = sub.add_parser("datalab-ingest", help="Alias of ingest (Datalab is already default)")
    d.add_argument("file")
    d.add_argument("--mode", default=None)
    d.set_defaults(func=cmd_datalab_ingest)

    lookup_p = sub.add_parser(
        "lookup", help="Deprecated — use rg/cat on kb/projects/<id>/wiki/"
    )
    lookup_p.add_argument("query")
    lookup_p.set_defaults(func=cmd_lookup)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
