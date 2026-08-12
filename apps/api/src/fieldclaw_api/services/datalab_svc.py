"""Datalab PDF/doc → markdown (default extract engine for FieldClaw)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

from fieldclaw_api.config import settings

DATALAB_CONVERT_URL = "https://www.datalab.to/api/v1/convert"


def _api_key() -> str:
    key = (os.environ.get("DATALAB_API_KEY") or "").strip()
    if key:
        return key
    hermes_env = settings.hermes_home / ".env"
    if hermes_env.exists():
        for line in hermes_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATALAB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _mode() -> str:
    mode = (os.environ.get("DATALAB_MODE") or "").strip()
    if mode:
        return mode
    hermes_env = settings.hermes_home / ".env"
    if hermes_env.exists():
        for line in hermes_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATALAB_MODE="):
                return line.split("=", 1)[1].strip() or "balanced"
    return "balanced"


def available() -> bool:
    return bool(_api_key())


def to_markdown(doc_path: Path, *, mode: str | None = None) -> str:
    """Convert PDF/doc to markdown via Datalab. Raises on failure."""
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("DATALAB_API_KEY not set")

    mode = mode or _mode()
    headers = {"X-API-Key": api_key}
    with doc_path.open("rb") as f, httpx.Client(timeout=180.0) as client:
        resp = client.post(
            DATALAB_CONVERT_URL,
            headers=headers,
            files={"file": (doc_path.name, f)},
            data={
                "output_format": "markdown",
                "mode": mode,
                "paginate": "true",
                "token_efficient_markdown": "true",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        check_url = body.get("request_check_url")
        if not check_url:
            raise RuntimeError(f"datalab: no request_check_url in {body}")

        for _ in range(300):
            result = client.get(check_url, headers=headers).json()
            status = result.get("status")
            if status == "complete":
                if not result.get("success", True):
                    raise RuntimeError(f"datalab failed: {result.get('error')}")
                md = (result.get("markdown") or "").strip()
                return f"# {doc_path.stem}\n\n{md}\n"
            if status == "failed":
                raise RuntimeError(f"datalab failed: {result.get('error')}")
            time.sleep(2)
    raise TimeoutError("datalab convert timed out")


def pdf_to_markdown(doc_path: Path) -> tuple[str, str]:
    """Prefer Datalab; fall back to pypdf only if Datalab unavailable/fails.

    Returns (markdown, engine) where engine is 'datalab' or 'pypdf'.
    """
    if available():
        try:
            return to_markdown(doc_path), "datalab"
        except Exception as e:
            # last-resort fallback — noisy but better than failing ingest
            from pypdf import PdfReader

            reader = PdfReader(str(doc_path))
            parts = [
                f"# {doc_path.stem}\n",
                f"\n<!-- datalab failed: {e} — pypdf fallback -->\n",
            ]
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                parts.append(f"\n## Page {i}\n\n{text.strip()}\n")
            return "\n".join(parts), "pypdf"

    from pypdf import PdfReader

    reader = PdfReader(str(doc_path))
    parts = [
        f"# {doc_path.stem}\n",
        "\n<!-- DATALAB_API_KEY missing — pypdf fallback -->\n",
    ]
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"\n## Page {i}\n\n{text.strip()}\n")
    return "\n".join(parts), "pypdf"
