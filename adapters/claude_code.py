"""
claude_code.py - Adapter para Claude Code CLI
=============================================
Traduce los eventos de Claude Code al formato comun del Motor.

Formato nativo de Claude Code (stdin de hooks):
  PostToolUse:
    {"tool_name": ..., "tool_input": {...}, "tool_result": ...,
     "session_id": ..., "hook_event_name": "PostToolUse", "cwd": ...,
     "exit_code": ...}

  UserPromptSubmit:
    {"prompt": ..., "session_id": ..., "hook_event_name": "UserPromptSubmit",
     "cwd": ...}

  Stop:
    {"session_id": ..., "hook_event_name": "Stop",
     "transcript_path": ..., "last_assistant_message": ...,
     "cwd": ..., "stop_hook_active": bool}

  SessionStart (en Claude Code se llama PreToolUse o no existe como evento
  dedicado; se simula leyendo context al inicio):
    {"session_id": ..., "hook_event_name": "SessionStart" (si aplica)}
"""

import json
from datetime import datetime, timezone

from .base_adapter import BaseAdapter

# Mapeo de nombres de eventos nativos de Claude Code al formato comun
_EVENT_MAP = {
    "UserPromptSubmit": "user_message",
    "PostToolUse":      "tool_used",
    "PreToolUse":       "pre_tool",     # para uso futuro
    "Stop":             "session_end",
    "SessionStart":     "session_start",
    # Variantes en minusculas
    "userpromptsubmit": "user_message",
    "posttooluse":      "tool_used",
    "pretooluse":       "pre_tool",
    "stop":             "session_end",
    "sessionstart":     "session_start",
}


class ClaudeCodeAdapter(BaseAdapter):
    """Adapter para Claude Code CLI (Anthropic)."""

    def get_cli_name(self) -> str:
        return "claude_code"

    def parse_stdin(self, raw: str) -> dict:
        """
        Parsea stdin JSON de Claude Code y retorna formato comun.
        """
        try:
            native = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, Exception):
            return {}

        hook_event = native.get("hook_event_name", "")
        event_type = _EVENT_MAP.get(hook_event, _EVENT_MAP.get(hook_event.lower(), ""))

        # Si no se pudo mapear, intentar inferir del contenido
        if not event_type:
            event_type = self._infer_event_type(native)

        common = {
            "event":       event_type,
            "session_id":  native.get("session_id", ""),
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "cwd":         native.get("cwd", ""),
            "_native":     native,   # guardar original para acceso por hooks
        }

        # Campos especificos por evento
        if event_type == "user_message":
            common["prompt"] = native.get("prompt", "")

        elif event_type == "tool_used":
            common["tool_name"]   = native.get("tool_name", "")
            common["tool_input"]  = native.get("tool_input", {})
            common["tool_output"] = str(native.get("tool_result",
                                        native.get("tool_output", "")))
            common["exit_code"]   = native.get("exit_code")

        elif event_type == "session_end":
            common["transcript_path"]      = native.get("transcript_path", "")
            common["last_assistant_message"] = native.get("last_assistant_message", "")
            common["stop_hook_active"]     = native.get("stop_hook_active", False)

        return common

    def get_hook_type(self, data: dict) -> str:
        """Retorna el tipo de evento del dict de formato comun."""
        return data.get("event", "")

    def _infer_event_type(self, native: dict) -> str:
        """
        Intenta inferir el tipo de evento cuando no hay hook_event_name.
        """
        if "prompt" in native:
            return "user_message"
        if "tool_name" in native or "tool_result" in native:
            return "tool_used"
        if "transcript_path" in native:
            return "session_end"
        return "unknown"
