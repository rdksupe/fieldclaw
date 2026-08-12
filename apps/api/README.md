# FieldClaw API

Package managed with **uv**; virtualenv is **`apps/api/.venv`** (do not use a global env).

```bash
cd apps/api
uv sync                          # create/update .venv from pyproject
source .venv/bin/activate        # optional; uv run works without it
cp .env.example .env             # set Telegram / Gmail when ready
uv run uvicorn fieldclaw_api.main:app --reload --host 127.0.0.1 --port 8000
```

Dashboard: http://127.0.0.1:8000/  
Health: http://127.0.0.1:8000/health  
Spec: [docs/TECH_SPEC.md](../../docs/TECH_SPEC.md)

```bash
# API smoke (server must be running)
uv run pytest ../../tests/e2e/test_local_api.py -v
```
