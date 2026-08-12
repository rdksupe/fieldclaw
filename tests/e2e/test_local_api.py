"""Local API smoke (no Telegram/SMTP — those need real credentials).

Run from apps/api:
  uv run pytest ../../tests/e2e/test_local_api.py -v
"""

from pathlib import Path

import httpx
import pytest

BASE = "http://127.0.0.1:8000"
KEY = {"X-API-Key": "dev-key-change-me"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=KEY, timeout=30) as c:
        r = c.get("/health")
        if r.status_code != 200:
            pytest.skip("API not running on :8000 — start with: cd apps/api && uv run fieldclaw-api")
        yield c


def test_e1_seed(client):
    r = client.post("/api/seed")
    assert r.status_code == 200
    data = r.json()
    assert "project_id" in data
    assert "zone-c" in data["zones"] or len(data["zones"]) >= 3
    client.project_id = data["project_id"]
    client.zones = data["zones"]


def test_e2_shortage_zone_amber_or_red(client):
    if not hasattr(client, "project_id"):
        test_e1_seed(client)
    pid = client.project_id
    zone_c = client.zones.get("zone-c")
    r = client.post(
        f"/api/projects/{pid}/events",
        json={
            "type": "shortage.raised",
            "zone_id": zone_c,
            "source": "api",
            "payload": {"text": "Rebar short", "material": "rebar", "urgency": "high"},
        },
    )
    assert r.status_code == 200
    types = [e["type"] for e in r.json()]
    assert "shortage.raised" in types
    assert "po.matched" in types
    zones = client.get(f"/api/projects/{pid}/zones").json()
    zc = next(z for z in zones if z["id"] == zone_c)
    assert zc["status"] in ("red", "amber")


def test_e6_kaggle_replay_and_reset(client):
    if not hasattr(client, "project_id"):
        test_e1_seed(client)
    pid = client.project_id
    client.post(f"/api/sim/kaggle_site/reset?project_id={pid}")
    r = client.post(f"/api/sim/kaggle_site/play?project_id={pid}&speed=100")
    assert r.status_code == 200
    import time

    time.sleep(2.5)
    events = client.get(f"/api/projects/{pid}/events", params={"source": "sim.kaggle_site"}).json()
    assert len(events) >= 1
    client.post(f"/api/sim/kaggle_site/reset?project_id={pid}")
    events2 = client.get(f"/api/projects/{pid}/events", params={"source": "sim.kaggle_site"}).json()
    assert events2 == []


def test_e7_wiki_fs_direct(tmp_path):
    """Wiki is Hermes/FS-owned — exercise wiki_fs.py, not FieldClaw /wiki/*."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    wiki_fs = root / "apps" / "hermes-skill" / "fieldclaw" / "wiki_fs.py"
    md = tmp_path / "po-note.md"
    md.write_text("# PO-9905 Rebar\n\nAcme Steel delivery for Zone C.\n", encoding="utf-8")
    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "FIELDCLAW_KB_DIR": str(tmp_path / "kb")}
    (tmp_path / "kb").mkdir()
    r = subprocess.run(
        [sys.executable, str(wiki_fs), "ingest", str(md)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    r2 = subprocess.run(
        [sys.executable, str(wiki_fs), "lookup", "PO-9905 Zone C"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r2.returncode == 0, r2.stderr
    assert "PO-9905" in r2.stdout


def test_e8_daily_log(client):
    if not hasattr(client, "project_id"):
        test_e1_seed(client)
    pid = client.project_id
    r = client.get(f"/api/projects/{pid}/daily-log")
    assert r.status_code == 200
    assert "events" in r.json()
