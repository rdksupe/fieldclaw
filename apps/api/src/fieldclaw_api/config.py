from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api → repo root
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(REPO_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fieldclaw_api_key: str = "dev-key-change-me"
    fieldclaw_db_path: Path = REPO_ROOT / "data" / "fieldclaw.db"
    fieldclaw_proofs_dir: Path = REPO_ROOT / "data" / "proofs"
    fieldclaw_kb_dir: Path = REPO_ROOT / "kb"
    fieldclaw_sim_dir: Path = REPO_ROOT / "sim"
    fieldclaw_web_dir: Path = REPO_ROOT / "apps" / "web"
    fieldclaw_project_id: str | None = None

    telegram_bot_token: str | None = None
    telegram_foreman_chat_id: str | None = None
    telegram_super_chat_id: str | None = None
    telegram_bot_username: str = "kayaadmin_bot"
    telegram_foreman_bot_username: str = "kaya_foremenbot"

    agentmail_api_key: str | None = None
    hermes_home: Path = Path.home() / ".hermes-fieldclaw"
    hermes_cli: str = "hermes-fieldclaw"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_vlm_model: str | None = None
    smallest_api_key: str | None = None

    # OxBlue openlink (SPA app id is public; override if OxBlue issues a partner id)
    oxblue_app_id: str | None = None
    oxblue_openlink: str = "apidemo"
    oxblue_site_match: str = "Wilbarger"


settings = Settings()
