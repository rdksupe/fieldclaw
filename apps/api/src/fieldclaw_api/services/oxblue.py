"""OxBlue openlink stills + day movies for the site camera wall.

Construction cams are not RTSP. We mint a short-lived openlink session, pick
the Wilbarger views, and proxy the latest still plus the site MP4 so the UI
can loop it like a live wall.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from fieldclaw_api.config import settings

OXBLUE_API = "https://api.oxblue.com/v1"
DEFAULT_APP_ID = "fc18eb502cb52d060bd93897e21d9491"
WILBARGER_CAM_IDS = (
    "b137fc5fb52c29afceb56cbc07fa85dc",  # View 1
    "d3f74af63960cfe7fb4d2dcdf7e3aa81",  # View 2
    "a2f7efbd011f9845559ef7c96d77965d",  # View 3 (H)
    "c4f099a61bcd676e5cd2cdc60554755b",  # View 4
)
# Local demo only — cams never attach to any other mailbox.
WASTEWATER_INBOX = "fc-my-site8506@agentmail.to"

_session: dict[str, Any] = {"id": None, "at": 0.0}
_CACHE = Path("/tmp/fieldclaw-oxblue")
_SESSION_TTL = 8 * 60
_STILL_TTL = 20
_MOVIE_TTL = 30 * 60


def _app_id() -> str:
    return (settings.oxblue_app_id or DEFAULT_APP_ID).strip()


def _openlink() -> str:
    return (settings.oxblue_openlink or "apidemo").strip()


def _site_match() -> str:
    return (settings.oxblue_site_match or "Wilbarger").strip().lower()


def project_has_cameras(inbox_email: str | None) -> bool:
    return (inbox_email or "").strip().lower() == WASTEWATER_INBOX.lower()


def _headers(session_id: str | None = None) -> dict[str, str]:
    h = {
        "Accept": "application/json",
        "X-APP-ID": _app_id(),
        "Content-Type": "application/json",
    }
    if session_id:
        h["Authorization"] = f"Bearer {session_id}"
    return h


def _session_id() -> str:
    now = time.time()
    if _session["id"] and now - _session["at"] < _SESSION_TTL:
        return str(_session["id"])
    with httpx.Client(timeout=20.0) as client:
        r = client.post(
            f"{OXBLUE_API}/openlink-sessions",
            headers=_headers(),
            json={"openLink": _openlink()},
        )
        r.raise_for_status()
        sid = r.json().get("sessionID")
    if not sid:
        raise RuntimeError("OxBlue openlink-sessions returned no sessionID")
    _session["id"] = sid
    _session["at"] = now
    return str(sid)


def _list_cameras() -> list[dict[str, Any]]:
    sid = _session_id()
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{OXBLUE_API}/cameras", headers=_headers(sid))
        r.raise_for_status()
        data = r.json()
    return list(data.get("cameras") or [])


def _wanted(cam: dict[str, Any]) -> bool:
    cid = str(cam.get("id") or "")
    if cid in WILBARGER_CAM_IDS:
        return True
    blob = " ".join(
        str(cam.get(k) or "") for k in ("camName", "siteName", "location", "name")
    ).lower()
    needle = _site_match()
    return bool(needle) and needle in blob


def _label(cam: dict[str, Any]) -> str:
    name = str(cam.get("camName") or cam.get("name") or "Camera")
    if " - " in name:
        return name.split(" - ", 1)[-1].strip()
    return name


def list_site_cameras() -> list[dict[str, Any]]:
    cams = [c for c in _list_cameras() if _wanted(c)]
    order = {cid: i for i, cid in enumerate(WILBARGER_CAM_IDS)}
    cams.sort(key=lambda c: order.get(str(c.get("id")), 99))
    out = []
    for cam in cams[:4]:
        cid = str(cam.get("id") or "")
        out.append(
            {
                "id": cid,
                "name": cam.get("camName") or cam.get("name"),
                "label": _label(cam),
                "last_upload": cam.get("lastUpload"),
                "has_video": bool(cam.get("videoPathMP4")),
                "still_url": f"/api/cameras/{cid}/still",
                "video_url": f"/api/cameras/{cid}/video",
            }
        )
    return out


def _cam(cam_id: str) -> dict[str, Any]:
    for cam in _list_cameras():
        if str(cam.get("id")) == cam_id:
            return cam
    raise KeyError(cam_id)


def fetch_still(cam_id: str) -> tuple[bytes, str]:
    _CACHE.mkdir(parents=True, exist_ok=True)
    path = _CACHE / f"{cam_id}.jpg"
    if path.is_file() and time.time() - path.stat().st_mtime < _STILL_TTL:
        return path.read_bytes(), "image/jpeg"
    cam = _cam(cam_id)
    url = cam.get("slideshowPath") or cam.get("imagePath")
    if not url:
        raise RuntimeError(f"no still URL for camera {cam_id}")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(str(url))
        r.raise_for_status()
        data = r.content
    path.write_bytes(data)
    return data, r.headers.get("content-type") or "image/jpeg"


def cached_movie_path(cam_id: str) -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    dest = _CACHE / f"{cam_id}.mp4"
    if dest.is_file() and dest.stat().st_size > 1024:
        if time.time() - dest.stat().st_mtime < _MOVIE_TTL:
            return dest
    cam = _cam(cam_id)
    url = cam.get("videoPathMP4")
    if not url:
        raise RuntimeError(f"no movie URL for camera {cam_id}")
    tmp = dest.with_suffix(".part")
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        with client.stream("GET", str(url)) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(1024 * 64):
                    f.write(chunk)
    tmp.replace(dest)
    return dest
