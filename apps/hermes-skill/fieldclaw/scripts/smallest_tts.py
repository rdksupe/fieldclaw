#!/usr/bin/env python3
"""Hermes TTS command provider → Smallest AI Waves (Lightning v3.1).

Usage (Hermes substitutes paths):
  python smallest_tts.py --text-file {input_path} --out {output_path} [--voice {voice}]
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--text-file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--voice", default=os.environ.get("SMALLEST_VOICE_ID", "avery"))
    p.add_argument("--model", default=os.environ.get("SMALLEST_TTS_MODEL", "lightning_v3.1"))
    args = p.parse_args()

    api_key = os.environ.get("SMALLEST_API_KEY", "").strip()
    if not api_key:
        print("SMALLEST_API_KEY not set", file=sys.stderr)
        return 2

    with open(args.text_file, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print("empty text", file=sys.stderr)
        return 2

    import json

    body = json.dumps(
        {
            "text": text[:4000],
            "voice_id": args.voice,
            "model": args.model,
            "sample_rate": 24000,
            "speed": 1.0,
            "language": "en",
            "output_format": "mp3",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.smallest.ai/waves/v1/tts",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg, audio/wav, application/json, */*",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"smallest TTS HTTP {e.code}: {err[:500]}", file=sys.stderr)
        return 1

    # Some responses wrap base64 JSON; prefer raw audio bytes
    if "json" in ctype and data[:1] == b"{":
        payload = json.loads(data.decode("utf-8"))
        import base64

        audio_b64 = payload.get("audio") or payload.get("data") or ""
        if not audio_b64:
            print(f"unexpected JSON: {payload!r}"[:400], file=sys.stderr)
            return 1
        data = base64.b64decode(audio_b64)

    out = args.out
    with open(out, "wb") as f:
        f.write(data)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
