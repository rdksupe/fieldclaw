#!/usr/bin/env bash
# Provision a role Hermes profile (foreman) served by the multiplexing gateway.
set -euo pipefail

ROLE="${1:-}"
BOT_TOKEN="${2:-}"
REPO="${FIELDCLAW_REPO:-/home/rdksupe/building_shit/buildsync}"
MUX_HOME="${HERMES_MUX_HOME:-$HOME/.hermes-fieldclaw}"
SKILL_DIR="$REPO/apps/hermes-skill/fieldclaw"
PLUGIN_SRC="$REPO/deploy/hermes/plugins/protect-identity"
HERMES_BIN="${HERMES_BIN:-/home/rdksupe/building_shit/hermes-agent/.venv/bin/hermes}"

if [[ "$ROLE" != "foreman" ]]; then
  echo "Usage: $0 foreman [<telegram_bot_token>]" >&2
  echo "  Supervisor stays on $MUX_HOME; this creates ~/.hermes-fc-foreman" >&2
  exit 2
fi

PROFILE_HOME="$HOME/.hermes-fc-foreman"
mkdir -p "$PROFILE_HOME"/{memories,skills,cron,sessions,logs,plugins}
mkdir -p "$MUX_HOME/plugins" "$MUX_HOME/profiles"

echo "==> Seeding foreman profile at $PROFILE_HOME"
SOUL_SRC="$REPO/deploy/hermes/identity/SOUL.foreman.md"
cp "$SOUL_SRC" "$PROFILE_HOME/SOUL.md"
for f in USER.md MEMORY.md; do
  src="$REPO/deploy/hermes/identity/$f"
  [[ -f "$src" ]] && cp "$src" "$PROFILE_HOME/memories/$f"
done
[[ -f "$REPO/AGENTS.md" ]] && ln -sfn "$REPO/AGENTS.md" "$PROFILE_HOME/AGENTS.md"
ln -sfn "$SKILL_DIR" "$PROFILE_HOME/skills/fieldclaw"
ln -sfn "$PLUGIN_SRC" "$PROFILE_HOME/plugins/protect-identity"
ln -sfn "$PLUGIN_SRC" "$MUX_HOME/plugins/protect-identity"

# Pull shared secrets from multiplexer .env
API_KEY=""; DATALAB=""; MEM0=""; FIREWORKS=""; OPENROUTER=""
BASE_URL="http://127.0.0.1:8000"
MODEL="accounts/fireworks/models/deepseek-v4-flash-0731"
if [[ -f "$MUX_HOME/.env" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$MUX_HOME/.env"; set +a
  API_KEY="${FIELDCLAW_API_KEY:-}"
  BASE_URL="${FIELDCLAW_BASE_URL:-$BASE_URL}"
  DATALAB="${DATALAB_API_KEY:-}"
  MEM0="${MEM0_API_KEY:-}"
  FIREWORKS="${FIREWORKS_API_KEY:-}"
  OPENROUTER="${OPENROUTER_API_KEY:-}"
fi

if [[ -z "$BOT_TOKEN" ]]; then
  BOT_TOKEN="${TELEGRAM_FOREMAN_BOT_TOKEN:-}"
fi
TOKEN_NOTE=""
if [[ -z "$BOT_TOKEN" ]]; then
  BOT_TOKEN="REPLACE_WITH_FOREMAN_BOT_TOKEN"
  TOKEN_NOTE="WARNING: set TELEGRAM_BOT_TOKEN in $PROFILE_HOME/.env then restart mux gateway"
fi

# Clone mux config, force no multiplex on child, enable protect-identity
python3 - "$MUX_HOME/config.yaml" "$PROFILE_HOME/config.yaml" <<'PY'
import sys, yaml
from pathlib import Path
mux_path, dst_path = Path(sys.argv[1]), Path(sys.argv[2])
cfg = {}
if mux_path.exists():
    cfg = yaml.safe_load(mux_path.read_text()) or {}
gw = cfg.setdefault("gateway", {})
gw["multiplex_profiles"] = False
plug = cfg.setdefault("plugins", {})
enabled = list(plug.get("enabled") or [])
if "protect-identity" not in enabled:
    enabled.append("protect-identity")
plug["enabled"] = enabled
plug.setdefault("disabled", [])
# Foreman personality hint
agent = cfg.setdefault("agent", {})
pers = agent.setdefault("personalities", {})
pers["fieldclaw-foreman"] = (
    "You are Foreman Claw. Capture field reports, project into FieldClaw, "
    "confirm briefly. Do not invent site facts. Escalate safety."
)
display = cfg.setdefault("display", {})
display["personality"] = "fieldclaw-foreman"
dst_path.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))
print("wrote", dst_path)
PY

# Ensure mux has protect-identity + multiplex on
python3 - "$MUX_HOME/config.yaml" <<'PY'
import sys, yaml
from pathlib import Path
p = Path(sys.argv[1])
cfg = yaml.safe_load(p.read_text()) or {}
gw = cfg.setdefault("gateway", {})
gw["multiplex_profiles"] = True
plug = cfg.setdefault("plugins", {})
enabled = list(plug.get("enabled") or [])
if "protect-identity" not in enabled:
    enabled.append("protect-identity")
plug["enabled"] = enabled
p.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))
print("mux multiplex + protect-identity ok")
PY

cat > "$PROFILE_HOME/.env" <<EOF
HERMES_HOME=$PROFILE_HOME
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
FIELDCLAW_BASE_URL=$BASE_URL
FIELDCLAW_API_KEY=$API_KEY
FIELDCLAW_KB_DIR=$REPO/kb
DATALAB_API_KEY=$DATALAB
DATALAB_MODE=balanced
MEM0_API_KEY=$MEM0
FIREWORKS_API_KEY=$FIREWORKS
OPENROUTER_API_KEY=$OPENROUTER
EOF
chmod 600 "$PROFILE_HOME/.env"

WRAPPER="$HOME/.local/bin/hermes-fc-foreman"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
export HERMES_HOME="$PROFILE_HOME"
if [[ -f "\$HERMES_HOME/.env" ]]; then
  set -a; source "\$HERMES_HOME/.env"; set +a
fi
exec "$HERMES_BIN" "\$@"
EOF
chmod +x "$WRAPPER"

ln -sfn "$PROFILE_HOME" "$MUX_HOME/profiles/foreman"

# Pairing-only DMs, no email chat adapter, cron gated on a live project.
"$REPO/deploy/hermes/harden_profile.sh" "$PROFILE_HOME"

echo ""
echo "=== Foreman role provisioned ==="
echo "profile:  $PROFILE_HOME"
echo "wrapper:  $WRAPPER"
echo "mux link: $MUX_HOME/profiles/foreman"
[[ -n "$TOKEN_NOTE" ]] && echo "$TOKEN_NOTE"
echo "Restart multiplexer: hermes-fieldclaw gateway run --replace"
echo "Do NOT run gateway start on the foreman profile."
