"""
ollama.py - Adapter para Ollama (modelos locales: Qwen3, Llama, Mistral, etc.)
===============================================================================
Conecta el Motor_IA con cualquier modelo servido por Ollama.

Uso directo:
    python ollama_chat.py --model qwen3:4b

API Ollama usada:
    POST http://localhost:11434/api/chat
    {"model": "qwen3:4b", "messages": [...], "stream": false}

Sin dependencias externas - solo stdlib (urllib).
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

from .base_adapter import BaseAdapter
from config import (
    OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL, OLLAMA_TIMEOUT_SECS,
    OLLAMA_RAM_HIGH_GB, OLLAMA_RAM_MID_GB,
    OLLAMA_CTX_HIGH, OLLAMA_CTX_MID, OLLAMA_CTX_LOW,
)

# Alias para compatibilidad con imports existentes (ollama_chat.py usa DEFAULT_MODEL)
DEFAULT_MODEL = OLLAMA_DEFAULT_MODEL


class OllamaAdapter(BaseAdapter):
    """
    Adapter para Ollama - modelos locales.

    Implementa BaseAdapter para consistencia con el Motor,
    y agrega metodos de chat directo para uso interactivo.
    """

    def __init__(self, model: str = OLLAMA_DEFAULT_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.model    = model
        self.base_url = base_url.rstrip("/")

    # -- BaseAdapter interface -------------------------------------------------

    def get_cli_name(self) -> str:
        return f"ollama/{self.model}"

    def parse_stdin(self, raw: str) -> dict:
        """
        Ollama no genera hooks propios.
        Parsea entrada en formato JSON o texto plano.
        """
        try:
            native = json.loads(raw) if raw.strip() else {}
        except Exception:
            native = {"prompt": raw.strip()}

        return {
            "event":      "user_message",
            "session_id": native.get("session_id", ""),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "cwd":        native.get("cwd", ""),
            "prompt":     native.get("prompt", native.get("message", "")),
            "_native":    native,
            "_adapter":   "ollama",
        }

    def get_hook_type(self, data: dict) -> str:
        return data.get("event", "user_message")

    # -- Disponibilidad --------------------------------------------------------

    def is_available(self) -> bool:
        """Verifica que Ollama este corriendo y el modelo este instalado."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data   = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                return any(self.model in m or m in self.model for m in models)
        except Exception:
            return False

    def list_models(self) -> list:
        """Retorna lista de modelos instalados en Ollama."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    # -- Chat ------------------------------------------------------------------

    def free_ram_gb(self) -> float:
        """Retorna GB de RAM libre (Windows). Retorna 99.0 si no puede medir."""
        try:
            import ctypes
            class _MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                             ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                             ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                             ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                             ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MEM()
            ms.dwLength = ctypes.sizeof(ms)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return ms.ullAvailPhys / (1024 ** 3)
        except Exception:
            return 99.0

    def recommended_ctx(self) -> int:
        """Recomienda num_ctx segun RAM disponible."""
        free = self.free_ram_gb()
        if free >= OLLAMA_RAM_HIGH_GB:
            return OLLAMA_CTX_HIGH
        if free >= OLLAMA_RAM_MID_GB:
            return OLLAMA_CTX_MID
        return OLLAMA_CTX_LOW

    def chat(
        self,
        messages: list,
        stream: bool = True,
        temperature: float = 0.7,
        num_ctx: int = 0,                        # 0 = auto segun RAM disponible
        timeout: int = OLLAMA_TIMEOUT_SECS,      # configurable via config.py
    ) -> str:
        """
        Envia mensajes a Ollama y retorna la respuesta completa.

        Args:
            messages:    [{"role": "system"|"user"|"assistant", "content": str}, ...]
            stream:      Si True, imprime tokens en tiempo real
            temperature: 0.0 = deterministico, 1.0 = creativo
            num_ctx:     Ventana de contexto en tokens

        Returns:
            Texto completo de respuesta del modelo.

        Raises:
            ConnectionError: si Ollama no esta corriendo
        """
        ctx = num_ctx if num_ctx > 0 else self.recommended_ctx()
        payload = {
            "model":    self.model,
            "messages": messages,
            "stream":   stream,
            "options":  {
                "temperature": temperature,
                "num_ctx":     ctx,
            },
        }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req  = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if stream:
                    return self._collect_stream(resp)
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "")
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"No se pudo conectar a Ollama en {self.base_url}.\n"
                f"Ejecuta primero: ollama serve\n"
                f"Error: {e}"
            )

    def _collect_stream(self, resp) -> str:
        """Lee el stream de tokens, los imprime en tiempo real y retorna el texto completo."""
        full = []
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    print(token, end="", flush=True)
                    full.append(token)
                if chunk.get("done"):
                    break
            except Exception:
                continue
        print()  # newline final
        return "".join(full)

    # -- System prompt ---------------------------------------------------------

    def build_system_prompt(self, kb_context: str = "", extra: str = "") -> str:
        """
        Construye el system prompt con el contexto del Motor inyectado.

        Args:
            kb_context: Contexto de la KB (patrones, reglas, historial)
            extra:      Instrucciones adicionales
        """
        parts = [
            "Eres un asistente de automatizacion especializado.",
            "Responde siempre en espanol.",
            "Basa tus respuestas en el conocimiento inyectado cuando sea relevante.",
        ]

        if kb_context:
            parts.append("\n--- CONOCIMIENTO INYECTADO ---")
            parts.append(kb_context)
            parts.append("--- FIN CONOCIMIENTO ---")

        if extra:
            parts.append(f"\n{extra}")

        return "\n".join(parts)
