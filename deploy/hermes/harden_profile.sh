#!/usr/bin/env bash
# Harden a FieldClaw Hermes profile so it costs nothing and touches nothing
# until a real project exists. Idempotent — safe to re-run after any provision.
#
#   deploy/hermes/harden_profile.sh [profile_home]
#
# Defaults to ~/.hermes-fieldclaw. Override the Hermes checkout with HERMES_SRC.
#
# Applies four fixes:
#   1. Install the cron wake gate and attach it to every agent-backed job, so a
#      tick with no project skips the agent instead of burning a model call.
#   2. Disable the Hermes email *chat* adapter. FieldClaw parses mail through
#      the mail-poll cron against the AgentMail REST API; leaving EMAIL_* set
#      also makes Hermes auto-reply to site mail as if it were a DM.
#   3. Clear TELEGRAM_ALLOWED_USERS so DMs go through the pairing handshake.
#   4. Remove duplicate top-level skill copies that shadow the fieldclaw store
#      and make cron fail with "Ambiguous skill name".
set -euo pipefail

PROFILE_HOME="${1:-$HOME/.hermes-fieldclaw}"
REPO="${FIELDCLAW_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
GATE_SRC="$REPO/deploy/hermes/scripts/fc_gate.py"

if [[ ! -d "$PROFILE_HOME" ]]; then
  echo "profile home not found: $PROFILE_HOME" >&2
  exit 2
fi
if [[ ! -f "$GATE_SRC" ]]; then
  echo "gate script not found: $GATE_SRC" >&2
  exit 2
fi

# Hermes checkout — needed to import cron.jobs for the gate attachment.
if [[ -z "${HERMES_SRC:-}" ]]; then
  for candidate in /opt/hermes-agent "$HOME/building_shit/hermes-agent" \
                   /home/rdksupe/building_shit/hermes-agent; do
    [[ -d "$candidate/cron" ]] && { HERMES_SRC="$candidate"; break; }
  done
fi
PY_BIN="python3"
[[ -n "${HERMES_SRC:-}" && -x "$HERMES_SRC/.venv/bin/python" ]] && PY_BIN="$HERMES_SRC/.venv/bin/python"

echo "==> Hardening $PROFILE_HOME"

echo "--> 1. cron wake gate"
mkdir -p "$PROFILE_HOME/scripts"
install -m 0644 "$GATE_SRC" "$PROFILE_HOME/scripts/fc_gate.py"
echo "    installed $PROFILE_HOME/scripts/fc_gate.py"

if [[ -n "${HERMES_SRC:-}" && -f "$PROFILE_HOME/cron/jobs.json" ]]; then
  HERMES_HOME="$PROFILE_HOME" "$PY_BIN" - "$HERMES_SRC" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from cron.jobs import list_jobs, update_job

for job in list_jobs(include_disabled=True):
    # Never clobber a job that already carries its own pre-check script.
    if job.get("no_agent") or (job.get("script") or "fc_gate.py") != "fc_gate.py":
        continue
    if job.get("script") != "fc_gate.py":
        update_job(job["id"], {"script": "fc_gate.py"})
    print(f"    gated {job['name']}")
PY
else
  echo "    no cron jobs yet (or HERMES_SRC unset) — gate installed for later"
fi

echo "--> 2/3. email chat adapter off, Telegram allowlist cleared"
if [[ -f "$PROFILE_HOME/.env" ]]; then
  "$PY_BIN" - "$PROFILE_HOME/.env" <<'PY'
import sys
from pathlib import Path

# These four enable the email chat adapter; the rest are commented for symmetry.
DISABLE = {"EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_IMAP_HOST", "EMAIL_IMAP_PORT",
           "EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT", "EMAIL_HOME_ADDRESS"}
MARKER = "# disabled-for-fieldclaw "

path = Path(sys.argv[1])
out, changed = [], []
for line in path.read_text().splitlines():
    key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
    if key in DISABLE:
        out.append(MARKER + line)
        changed.append(key)
    elif key == "TELEGRAM_ALLOWED_USERS" and line.split("=", 1)[1].strip():
        out.append("TELEGRAM_ALLOWED_USERS=")
        changed.append("TELEGRAM_ALLOWED_USERS")
    else:
        out.append(line)
path.write_text("\n".join(out) + "\n")
print("    changed:", ", ".join(changed) if changed else "(already hardened)")
PY
  chmod 600 "$PROFILE_HOME/.env"
else
  echo "    no .env yet — nothing to disable"
fi

echo "--> 4. duplicate skills"
SKILLS="$PROFILE_HOME/skills"
DUPES=()
if [[ -d "$SKILLS/fieldclaw" ]]; then
  # Only SKILL.md-bearing dirs are skills; fieldclaw/ also holds scripts/ etc.
  while IFS= read -r nested; do
    name="$(basename "$nested")"
    [[ -f "$SKILLS/$name/SKILL.md" ]] && DUPES+=("$name")
  done < <(find -L "$SKILLS/fieldclaw" -mindepth 2 -maxdepth 2 -name SKILL.md -printf '%h\n' 2>/dev/null)
fi
if (( ${#DUPES[@]} )); then
  BACKUP="$SKILLS/.dup-backup-$(date +%Y%m%d%H%M%S)"
  mkdir -p "$BACKUP"
  for name in "${DUPES[@]}"; do
    mv "$SKILLS/$name" "$BACKUP/$name"
    echo "    moved $name -> $BACKUP"
  done
  echo "    NOTE: review $BACKUP if those copies held newer edits"
else
  echo "    none"
fi

echo ""
echo "=== $PROFILE_HOME hardened ==="
echo "Crons stay silent until GET /api/projects returns a project."
echo "Telegram DMs now require pairing: hermes-fieldclaw pairing approve telegram <CODE>"
