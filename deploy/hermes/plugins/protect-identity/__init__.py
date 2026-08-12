"""Block writes to SOUL.md / config.yaml / .env under HERMES_HOME."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

PROTECTED_NAMES = frozenset({"SOUL.md", "config.yaml", ".env"})

# Tools that carry an explicit filesystem path argument.
_PATH_TOOLS = {
    "write_file": ("path",),
    "patch": ("path",),
    "delete_file": ("path",),
    "move_file": ("src", "dest", "path", "from_path", "to_path"),
}

_WRITEISH_TERMINAL = re.compile(
    r"(?:^|[;&|]\s*|>\s*|>>\s*|tee\s+|sed\s+-i|truncate\s+|rm\s+|mv\s+|cp\s+|install\s+|"
    r"python[3]?\s+-c|printf\s+|echo\s+|cat\s*>|dd\s+)",
    re.IGNORECASE,
)


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()).expanduser().resolve()
    except Exception:
        raw = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
        return Path(raw).expanduser().resolve()


def _resolve(path: str) -> Optional[Path]:
    if not path or not isinstance(path, str):
        return None
    try:
        return Path(os.path.expanduser(path)).resolve()
    except Exception:
        return None


def _is_protected_path(path: str) -> bool:
    resolved = _resolve(path)
    if resolved is None:
        return False
    if resolved.name not in PROTECTED_NAMES:
        return False
    home = _hermes_home()
    try:
        resolved.relative_to(home)
        return True
    except ValueError:
        # Also catch absolute/relative forms that still land on the basename
        # under HERMES_HOME after expand (e.g. "~/.hermes-fieldclaw/SOUL.md").
        return str(resolved).startswith(str(home) + os.sep)


def _terminal_targets_protected(command: str) -> bool:
    if not command or not isinstance(command, str):
        return False
    if not _WRITEISH_TERMINAL.search(command):
        # Still block obvious direct overwrites even if pattern missed
        if not any(name in command for name in PROTECTED_NAMES):
            return False
    home = _hermes_home()
    home_s = str(home)
    for name in PROTECTED_NAMES:
        if name not in command:
            continue
        # Heuristic: command mentions the protected file near HERMES_HOME / ~
        if (
            home_s in command
            or "$HERMES_HOME" in command
            or "${HERMES_HOME}" in command
            or "~/.hermes" in command
            or name == command.strip()
            or f"/{name}" in command
            or f" {name}" in command
            or command.strip().endswith(name)
        ):
            return True
    return False


def protect_identity(tool_name: str, args: dict, **kwargs: Any):
    args = args or {}
    if tool_name in _PATH_TOOLS:
        for key in _PATH_TOOLS[tool_name]:
            val = args.get(key)
            if isinstance(val, str) and _is_protected_path(val):
                return {
                    "action": "block",
                    "message": (
                        f"Refusing to modify operator-owned identity/security file "
                        f"({Path(val).name}). Edit SOUL.md / config.yaml / .env outside the agent."
                    ),
                }
    if tool_name == "terminal":
        cmd = args.get("command") or args.get("cmd") or ""
        if _terminal_targets_protected(str(cmd)):
            return {
                "action": "block",
                "message": (
                    "Refusing terminal mutation of SOUL.md / config.yaml / .env under "
                    "HERMES_HOME. Those files are operator-owned."
                ),
            }
    return None


def register(ctx):
    ctx.register_hook("pre_tool_call", protect_identity)
