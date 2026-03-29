"""
gemini.py - Adapter para Gemini CLI (Google) - stub
====================================================
Gemini CLI no tiene sistema de hooks documentado publicamente.
Este adapter es un placeholder para cuando Google exponga hooks.

Por ahora: retorna datos basicos del JSON que pueda llegar.

TODO: actualizar cuando Gemini CLI publique su API de extensiones.

Referencias:
  - https://cloud.google.com/gemini/docs (verificar actualizaciones)
  - Google Gemini Code Assist CLI
"""

import json
from datetime import datetime, timezone

from .base_adapter import BaseAdapter


class GeminiAdapter(BaseAdapter):
    """
    Adapter para Gemini CLI (Google).

    ESTADO: stub / placeholder.
    Retorna lo que pueda extraer del JSON recibido, con defaults seguros.
    """

    def get_cli_name(self) -> str:
        return "gemini"

    def parse_stdin(self, raw: str) -> dict:
        """
        Parsea stdin de Gemini CLI.
        Sin documentacion oficial de hooks, intenta extraer campos comunes.
        """
        try:
            native = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, Exception):
            native = {}

        # Intento best-effort: extraer lo que se pueda
        event_type = self._infer_event_type(native)

        common = {
            "event":      event_type,
            "session_id": native.get("session_id",
                          native.get("id",
                          native.get("conversation_id", ""))),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "cwd":        native.get("cwd", native.get("working_dir", "")),
            "_native":    native,
            "_adapter":   "gemini_stub",
        }

        if event_type == "user_message":
            common["prompt"] = (native.get("prompt") or
                                native.get("user_message") or
                                native.get("message") or "")

        elif event_type == "tool_used":
            common["tool_name"]   = (native.get("tool_name") or
                                     native.get("tool") or "")
            common["tool_input"]  = (native.get("tool_input") or
                                     native.get("input") or {})
            common["tool_output"] = str(native.get("tool_result") or
                                        native.get("output") or "")
            common["exit_code"]   = native.get("exit_code")

        elif event_type == "session_end":
            common["transcript_path"] = native.get("transcript_path", "")

        return common

    def get_hook_type(self, data: dict) -> str:
        return data.get("event", "unknown")

    def _infer_event_type(self, native: dict) -> str:
        """Infiere el tipo de evento a partir del contenido disponible."""
        # Intentar mapear campos conocidos de Gemini
        event = native.get("event", native.get("type", native.get("hook", "")))
        mappings = {
            "message": "user_message",
            "user_message": "user_message",
            "prompt": "user_message",
            "tool_call": "tool_used",
            "function_call": "tool_used",
            "session_end": "session_end",
            "end": "session_end",
        }
        if event in mappings:
            return mappings[event]

        # Fallback por campos presentes
        if "prompt" in native or "user_message" in native:
            return "user_message"
        if "tool_name" in native or "tool" in native or "function_call" in native:
            return "tool_used"

        return "unknown"
