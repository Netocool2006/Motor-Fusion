"""
base_adapter.py - Interfaz abstracta para adapters de CLI
=========================================================
Cada CLI tiene su propia forma de disparar eventos.
El adapter traduce el formato nativo al formato comun del Motor.

Formato comun de eventos:
{
    "event": "session_start" | "tool_used" | "user_message" | "session_end",
    "session_id": str,
    "timestamp": str (ISO),
    # campos especificos por evento:
    "prompt": str,              # para user_message
    "tool_name": str,           # para tool_used
    "tool_input": dict,         # para tool_used
    "tool_output": str,         # para tool_used
    "exit_code": int | None,    # para tool_used
    "transcript_path": str,     # para session_end
    "cwd": str,                 # todos
}
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone


class BaseAdapter(ABC):
    """
    Interfaz base para todos los adapters de CLI.

    Cada CLI concreto (Claude Code, Gemini, etc.) implementa esta interfaz
    para que los hooks del Motor puedan funcionar de forma agnostica.
    """

    @abstractmethod
    def parse_stdin(self, raw: str) -> dict:
        """
        Parsea stdin del CLI y retorna dict en formato comun.

        Args:
            raw: Contenido crudo de stdin (generalmente JSON).

        Returns:
            dict en formato comun del Motor.
        """

    @abstractmethod
    def get_hook_type(self, data: dict) -> str:
        """
        Determina el tipo de evento a partir de los datos parseados.

        Returns:
            Uno de: "session_start" | "tool_used" | "user_message" | "session_end"
        """

    @abstractmethod
    def get_cli_name(self) -> str:
        """
        Retorna el identificador del CLI.

        Returns:
            Ejemplo: "claude_code", "gemini", "cursor", etc.
        """

    def normalize_event(self, data: dict) -> dict:
        """
        Asegura que el evento tenga los campos minimos requeridos.
        Puede ser sobreescrito por subclases para normalizacion adicional.
        """
        if "timestamp" not in data:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        if "session_id" not in data:
            data["session_id"] = ""
        if "cwd" not in data:
            data["cwd"] = ""
        if "event" not in data:
            data["event"] = self.get_hook_type(data)
        return data

    def is_valid_event(self, data: dict) -> bool:
        """
        Verifica si el evento tiene datos suficientes para procesarse.
        """
        return bool(data.get("event") and data.get("session_id"))
