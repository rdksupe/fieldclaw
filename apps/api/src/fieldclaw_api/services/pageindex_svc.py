"""PageIndex (VectifyAI) for large PDFs — tree index, not OpenKB wiki compile."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fieldclaw_api.config import settings

# Prefer sibling clone: …/building_shit/PageIndex
_DEFAULT_PI = Path(__file__).resolve().parents[5].parent / "PageIndex"
if not _DEFAULT_PI.is_dir():
    _DEFAULT_PI = Path("/home/rdksupe/building_shit/PageIndex")

PAGEINDEX_PAGE_THRESHOLD = int(os.environ.get("PAGEINDEX_PAGE_THRESHOLD", "8"))
PAGEINDEX_BYTES_THRESHOLD = int(
    os.environ.get("PAGEINDEX_BYTES_THRESHOLD", str(1_500_000))
)


def _pi_root() -> Path:
    env = os.environ.get("PAGEINDEX_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    return _DEFAULT_PI


def _llm_env() -> dict[str, str]:
    env = os.environ.copy()
    hermes_env = settings.hermes_home / ".env"
    if hermes_env.exists():
        for line in hermes_env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    # PageIndex / LiteLLM often want OPENAI_API_KEY; map OpenRouter
    if not (env.get("OPENAI_API_KEY") or "").strip():
        for alt in ("OPENROUTER_API_KEY", "LLM_API_KEY"):
            if (env.get(alt) or "").strip():
                env["OPENAI_API_KEY"] = env[alt].strip()
                break
    if (env.get("OPENROUTER_API_KEY") or "").strip() and not env.get("OPENAI_API_BASE"):
        # LiteLLM OpenRouter
        env.setdefault("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    return env


def should_use_pageindex(pdf_path: Path) -> bool:
    if pdf_path.suffix.lower() != ".pdf":
        return False
    if pdf_path.stat().st_size >= PAGEINDEX_BYTES_THRESHOLD:
        return True
    try:
        from pypdf import PdfReader

        n = len(PdfReader(str(pdf_path)).pages)
        return n >= PAGEINDEX_PAGE_THRESHOLD
    except Exception:
        return pdf_path.stat().st_size >= 500_000


def run_pageindex(pdf_path: Path, out_json: Path, *, flash: bool = True) -> dict:
    """Run PageIndex CLI; write tree JSON to out_json."""
    root = _pi_root()
    script = root / "run_pageindex.py"
    if not script.exists():
        return {"ok": False, "error": f"PageIndex not found at {root}"}

    env = _llm_env()
    # Prefer PageIndex venv (has PyPDF2 / litellm); fall back to system python3
    venv_py = root / ".venv" / "bin" / "python"
    py = (
        str(venv_py)
        if venv_py.is_file()
        else (shutil.which("python3") or sys.executable)
    )
    env["PYTHONPATH"] = str(root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    cmd = [py, str(script), "--pdf_path", str(pdf_path)]
    if flash:
        cmd.append("--flash")
        cmd.append("--no-summary")  # structure without LLM summaries
    model = env.get("PAGEINDEX_MODEL") or env.get("OPENROUTER_MODEL")
    if model:
        cmd.extend(["--model", model])

    # PageIndex writes next to PDF by default — run from out dir
    out_json.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        cmd,
        cwd=str(out_json.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    # Discover produced JSON near PDF or cwd
    stem = pdf_path.stem
    candidates = [
        out_json,
        out_json.parent / f"{stem}_structure.json",
        out_json.parent / f"{stem}_structure_flash.json",
        out_json.parent / f"{stem}.json",
        out_json.parent / "results" / f"{stem}_structure.json",
        out_json.parent / "results" / f"{stem}_structure_flash.json",
        pdf_path.with_name(f"{stem}_structure.json"),
        pdf_path.with_suffix(".json"),
    ]
    found = next((p for p in candidates if p.exists() and p.stat().st_size > 2), None)
    # also search cwd (+ results/) for newest matching json
    if not found:
        search_roots = [out_json.parent, out_json.parent / "results"]
        hits: list[Path] = []
        for root_dir in search_roots:
            if not root_dir.is_dir():
                continue
            hits.extend(root_dir.glob("*.json"))
        for p in sorted(hits, key=lambda x: x.stat().st_mtime, reverse=True):
            if stem.lower() in p.stem.lower() or "structure" in p.name:
                found = p
                break

    if found and found != out_json:
        shutil.copy2(found, out_json)
        found = out_json

    if proc.returncode != 0 and not (found and found.exists()):
        return {
            "ok": False,
            "exit_code": proc.returncode,
            "stderr": (proc.stderr or proc.stdout or "")[-1500:],
            "engine": "pageindex",
        }

    return {
        "ok": bool(found and found.exists()),
        "exit_code": proc.returncode,
        "path": str(found) if found else None,
        "stdout": (proc.stdout or "")[-800:],
        "stderr": (proc.stderr or "")[-800:],
        "engine": "pageindex-flash" if flash else "pageindex",
    }


def tree_summary_markdown(tree_path: Path, *, title: str, raw_name: str) -> str:
    """Human-readable outline from a PageIndex JSON tree."""
    try:
        data = json.loads(tree_path.read_text(encoding="utf-8"))
    except Exception as e:
        return (
            f"# {title}\n\nPageIndex tree at `{tree_path.name}` (parse error: {e}).\n"
        )

    lines = [
        f"# {title}",
        "",
        f"Source: `raw/{raw_name}`",
        f"PageIndex tree: `wiki/pageindex/{tree_path.name}`",
        "",
        "## Document outline",
        "",
    ]

    def walk(node: dict | list, depth: int = 0) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n, depth)
            return
        if not isinstance(node, dict):
            return
        title_n = (
            node.get("title") or node.get("name") or node.get("node_id") or "section"
        )
        start = node.get("start_index")
        end = node.get("end_index")
        summary = node.get("summary") or ""
        pad = "  " * depth
        span = ""
        if start is not None:
            span = f" (p.{start}" + (f"–{end}" if end is not None else "") + ")"
        lines.append(f"{pad}- **{title_n}**{span}")
        if summary and depth < 3:
            lines.append(f"{pad}  _{str(summary)[:240]}_")
        for key in ("nodes", "children", "structure"):
            if key in node:
                walk(node[key], depth + 1)

    # common shapes
    if isinstance(data, dict):
        if "structure" in data:
            walk(data["structure"])
        elif "nodes" in data:
            walk(data["nodes"])
        else:
            walk(data)
    else:
        walk(data)

    if len(lines) < 10:
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(data, indent=2)[:3000])
        lines.append("```")
    lines.append("")
    return "\n".join(lines)
