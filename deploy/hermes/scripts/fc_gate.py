#!/usr/bin/env python3
"""Cron wake gate for FieldClaw jobs.

Hermes runs this before building a job's prompt. When the last stdout line is
``{"wakeAgent": false}`` the agent run is skipped entirely — no model call, no
tokens. Anything else wakes the agent, and this script's stdout is injected as
context so the job does not have to spend a tool call resolving the project.

Gate: at least one project must exist in the FieldClaw API.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

def _from_env_file(name: str) -> str | None:
    """Fall back to the profile .env — the API address differs per host, so
    guessing localhost would silently gate every job off on a split deploy."""
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes-fieldclaw")
    try:
        with open(os.path.join(home, ".env"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == name:
                    return value.strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


BASE = (
    os.environ.get("FIELDCLAW_BASE_URL")
    or _from_env_file("FIELDCLAW_BASE_URL")
    or "http://127.0.0.1:8000"
).rstrip("/")
KEY = (
    os.environ.get("FIELDCLAW_API_KEY")
    or _from_env_file("FIELDCLAW_API_KEY")
    or "dev-key-change-me"
)

FIELDS = ("id", "name", "inbox_email", "kb_relpath")


def fetch_projects() -> list[dict]:
    req = urllib.request.Request(
        f"{BASE}/api/projects",
        headers={"X-API-Key": KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return data if isinstance(data, list) else []


def sleep_gate(reason: str) -> None:
    print(f"# fieldclaw gate: {reason}")
    print(json.dumps({"wakeAgent": False}))


try:
    projects = fetch_projects()
except Exception as exc:
    # API down or unreachable is not a reason to burn a model call.
    sleep_gate(f"API unreachable ({type(exc).__name__}: {exc})")
    raise SystemExit(0)

if not projects:
    sleep_gate("no projects registered — nothing to poll")
    raise SystemExit(0)

print("## Live FieldClaw projects (resolved by the cron gate, trust this list)")
for p in projects:
    print(json.dumps({k: p.get(k) for k in FIELDS}))
print(json.dumps({"wakeAgent": True}))
