import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fieldclaw_api.config import settings
from fieldclaw_api.db import init_db
from fieldclaw_api.routers.api import router as api_router
from fieldclaw_api.routers.auth import router as auth_router
from fieldclaw_api.services import ui_auth

log = logging.getLogger("fieldclaw")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings.fieldclaw_proofs_dir.mkdir(parents=True, exist_ok=True)
    (settings.fieldclaw_kb_dir / "raw").mkdir(parents=True, exist_ok=True)
    (settings.fieldclaw_kb_dir / "wiki").mkdir(parents=True, exist_ok=True)
    password = ui_auth.get_or_create_password()
    log.warning(
        "FieldClaw dashboard password: %s  (%s)", password, ui_auth.password_path()
    )
    yield


app = FastAPI(title="FieldClaw API", version="0.1.0", lifespan=lifespan)
# No allow_credentials: the dashboard is same-origin, so its cookie never needs
# a CORS grant, and "*" with credentials is rejected by browsers anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(api_router)


@app.get("/health")
def health():
    return {"ok": True, "service": "fieldclaw-api"}


web_dir = Path(settings.fieldclaw_web_dir)
assets_dir = web_dir / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/")
def dashboard():
    index = web_dir / "index.html"
    if not index.exists():
        return {"message": "dashboard missing", "path": str(index)}
    return FileResponse(index)
