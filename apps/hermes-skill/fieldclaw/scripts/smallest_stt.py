#!/usr/bin/env python3
"""Hermes STT command provider → Smallest AI Waves (Pulse).

Writes transcript to {output_path}.
  python smallest_stt.py --audio {input_path} --out {output_path}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--language", default=os.environ.get("SMALLEST_STT_LANGUAGE", "en"))
    p.add_argument("--model", default=os.environ.get("SMALLEST_STT_MODEL", "pulse"))
    args = p.parse_args()

    api_key = os.environ.get("SMALLEST_API_KEY", "").strip()
    if not api_key:
        print("SMALLEST_API_KEY not set", file=sys.stderr)
        return 2

    audio_path = args.audio
    with open(audio_path, "rb") as f:
        raw = f.read()
    if not raw:
        print("empty audio", file=sys.stderr)
        return 2

    qs = urllib.parse.urlencode(
        {
            "model": args.model or "pulse",
            "language": args.language or "en",
        }
    )
    url = f"https://api.smallest.ai/waves/v1/stt/?{qs}"
    req = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/octet-stream",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"smallest STT HTTP {e.code}: {err[:500]}", file=sys.stderr)
        return 1

    text = (
        payload.get("transcription")
        or payload.get("text")
        or payload.get("transcript")
        or ""
    )
    if isinstance(payload.get("segments"), list) and not text:
        text = " ".join(
            str(s.get("text", "")).strip() for s in payload["segments"] if isinstance(s, dict)
        ).strip()

    if not text:
        print(f"no transcript in response: {payload!r}"[:400], file=sys.stderr)
        return 1

    out = args.out
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
