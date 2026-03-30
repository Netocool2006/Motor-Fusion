# -*- coding: utf-8 -*-
"""
config.py - Configuracion centralizada del Motor_IA unificado
=============================================================
Todos los paths, constantes y parametros globales del proyecto.
Resolucion de directorio de datos: env MOTOR_IA_DATA > HOME/.adaptive_cli
> LOCALAPPDATA/ClaudeCode/.adaptive_cli > Path.home()/.adaptive_cli

Todos los directorios se crean automaticamente al importar este modulo.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
VERSION = "1.0.0-fusion"

# ---------------------------------------------------------------------------
# Resolucion del directorio de datos
# ---------------------------------------------------------------------------

def get_data_dir() -> Path:
    """
    Resuelve el directorio raiz de datos con la siguiente precedencia:
      1. Variable de entorno MOTOR_IA_DATA (si existe y es valida)
      2. HOME/.adaptive_cli
      3. LOCALAPPDATA/ClaudeCode/.adaptive_cli  (solo Windows)
      4. Path.home()/.adaptive_cli  (fallback absoluto)
    """
    # 1. Variable de entorno explicita
    env_val = os.environ.get("MOTOR_IA_DATA")
    if env_val:
        p = Path(env_val)
        if p.is_absolute():
            return p

    # 2. HOME/.adaptive_cli
    home = Path.home()
    candidate = home / ".adaptive_cli"
    if home != Path("/") and home != Path("."):
        return candidate

    # 3. LOCALAPPDATA (Windows)
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            return Path(local_app) / "ClaudeCode" / ".adaptive_cli"

    # 4. Fallback absoluto
    return Path.home() / ".adaptive_cli"


# ---------------------------------------------------------------------------
# Directorio raiz de datos
# ---------------------------------------------------------------------------
DATA_DIR: Path = get_data_dir()

# ---------------------------------------------------------------------------
# Subdirectorios
# ---------------------------------------------------------------------------
KNOWLEDGE_DIR: Path = DATA_DIR / "knowledge"
LOCK_DIR: Path      = DATA_DIR / "locks"
HOOK_STATE_DIR: Path = DATA_DIR / "hook_state"

# ---------------------------------------------------------------------------
# Archivos principales
# ---------------------------------------------------------------------------
LOG_FILE: Path              = DATA_DIR / "execution_log.jsonl"
EXECUTION_LOG: Path         = DATA_DIR / "execution_log.jsonl"   # alias
SESSION_HISTORY_FILE: Path  = DATA_DIR / "session_history.json"
EPISODIC_DB: Path           = DATA_DIR / "episodic_index.db"

# Dominios y conocimiento
DOMAINS_FILE: Path          = KNOWLEDGE_DIR / "domains.json"

# Memoria y aprendizaje
MEMORY_FILE: Path           = DATA_DIR / "learned_patterns.json"
ATTEMPTS_FILE: Path         = DATA_DIR / "task_attempts.json"

# Estado de iteracion
STATE_FILE: Path            = DATA_DIR / "iteration_state.json"
ACTIONS_LOG: Path           = DATA_DIR / "iteration_actions.jsonl"

# Clasificacion de mensaje actual (para post_tool_use)
MSG_TYPE_FILE: Path         = HOOK_STATE_DIR / "msg_type.json"

# Errores pendientes (para post_tool_use)
PENDING_ERRORS_FILE: Path   = HOOK_STATE_DIR / "pending_errors.json"

# SAP playbook
SAP_PLAYBOOK_DB: Path       = DATA_DIR / "sap_playbook.db"

# ---------------------------------------------------------------------------
# Archivos heredados de Motor 2 (hooks avanzados)
# ---------------------------------------------------------------------------
CO_OCCUR_FILE: Path         = DATA_DIR / "domain_cooccurrence.json"
MARKOV_FILE: Path           = DATA_DIR / "domain_markov.json"
CLASSIFY_CACHE: Path        = DATA_DIR / "classify_cache.json"
LAST_MSG_FILE: Path         = DATA_DIR / "last_user_message.txt"
NOTIFY_FILE: Path           = DATA_DIR / "last_learning.txt"
PROMPT_HIST_FILE: Path      = DATA_DIR / "prompt_history.jsonl"
INJECTION_FILE: Path        = DATA_DIR / "last_injection.json"
HINT_EFFECT_FILE: Path      = DATA_DIR / "hint_effectiveness.json"
FINGERPRINTS_FILE: Path     = DATA_DIR / "iter_fingerprints.json"
FAILURES_FILE: Path         = DATA_DIR / "pattern_failures.json"
DEBUG_LOG: Path             = DATA_DIR / "hook_debug.log"
ADAPTER_FILE: Path          = DATA_DIR / "adapter.json"

# ---------------------------------------------------------------------------
# Constantes de negocio
# ---------------------------------------------------------------------------
DEDUP_WINDOW_SECS: int       = 900    # 15 min - ventana de deduplicacion
ITERATION_GAP_SECS: int      = 15     # pausa minima entre iteraciones
ERROR_CORRELATION_WINDOW: int = 600   # 10 min - ventana correlacion errores
CONFIDENCE_DECAY_DAYS: int   = 30     # dias para decay de confianza

# ---------------------------------------------------------------------------
# Ollama adapter
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str          = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_DEFAULT_MODEL: str     = os.environ.get("OLLAMA_DEFAULT_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_SECS: int      = 300   # 5 min - timeout HTTP para respuestas largas
OLLAMA_RAM_HIGH_GB: float     = 4.0   # RAM minima para contexto alto
OLLAMA_RAM_MID_GB: float      = 3.0   # RAM minima para contexto medio
OLLAMA_CTX_HIGH: int          = 4096  # num_ctx con RAM alta
OLLAMA_CTX_MID: int           = 2048  # num_ctx con RAM media
OLLAMA_CTX_LOW: int           = 512   # num_ctx con RAM baja

# ---------------------------------------------------------------------------
# Hooks - clasificacion y cache
# ---------------------------------------------------------------------------
CACHE_TTL_SECS: int           = 7200  # 2 h - TTL de clasificacion de mensajes
CACHE_OVERLAP_THRESHOLD: float = 0.55 # 55% keywords en comun = cache hit
RECENT_HOURS: int             = 1     # ventana de contexto en session_start

# ---------------------------------------------------------------------------
# Learning memory
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD: float   = 0.6   # umbral de confianza para reutilizar patron
MAX_PENDING_ERRORS: int       = 15    # maximo de errores pendientes en buffer

# ---------------------------------------------------------------------------
# Domain detector
# ---------------------------------------------------------------------------
AUTO_ASSIGN_THRESHOLD: int    = 2     # >= 2 keywords -> asignar dominio automaticamente
SUGGEST_THRESHOLD: int        = 1     # >= 1 keyword -> sugerir dominio (sin auto-asignar)

# ---------------------------------------------------------------------------
# SAP Playbook
# ---------------------------------------------------------------------------
CONFIDENCE_DECAY_RATE: float  = 0.1   # 10% de decay por periodo sin uso

# ---------------------------------------------------------------------------
# Iteration learn
# ---------------------------------------------------------------------------
EXPLORE_THRESHOLD: int        = 3     # explores consecutivos sin accion -> busqueda proactiva

# ---------------------------------------------------------------------------
# Ollama chat (KB context)
# ---------------------------------------------------------------------------
MAX_KB_CHARS: int             = 3000  # ~750 tokens de contexto KB inyectado

# ---------------------------------------------------------------------------
# Auto-pruning (memory_pruner)
# ---------------------------------------------------------------------------
AUTO_PRUNE_ENABLED: bool           = True
AUTO_PRUNE_MIN_SUCCESS_RATE: float = 0.2   # < 20% exito = candidato a poda
AUTO_PRUNE_DAYS_UNUSED: int        = 90    # sin uso en 90 dias
AUTO_PRUNE_MIN_REUSES: int         = 0     # 0 reusos = sin valor demostrado

# ---------------------------------------------------------------------------
# Hint effectiveness feedback loop (hint_tracker)
# ---------------------------------------------------------------------------
HINT_EFFECTIVENESS_DECAY: float    = 0.7   # EMA: 70% peso historico, 30% nuevo dato

# ---------------------------------------------------------------------------
# Memory consolidation (memory_consolidator)
# ---------------------------------------------------------------------------
CONSOLIDATION_ENABLED: bool             = True
CONSOLIDATION_MIN_PATTERNS: int         = 5     # min patrones en tipo para consolidar
CONSOLIDATION_SIMILARITY_THRESHOLD: float = 0.7 # Jaccard >= 0.7 para fusionar

# ---------------------------------------------------------------------------
# Working memory (working_memory)
# ---------------------------------------------------------------------------
WORKING_MEMORY_MAX_ITEMS: int      = 50    # max items en sesion actual
WORKING_MEMORY_TTL_HOURS: int      = 24    # TTL antes de expirar automaticamente

# ---------------------------------------------------------------------------
# Auto-domain promotion (crear dominios dinamicamente por uso)
# ---------------------------------------------------------------------------
AUTO_DOMAIN_MIN_SESSIONS: int      = int(os.environ.get("AUTO_DOMAIN_MIN_SESSIONS", "3"))
# Minimo de mensajes de usuario en la sesion para que cuente como actividad significativa
AUTO_DOMAIN_MIN_MSGS: int          = int(os.environ.get("AUTO_DOMAIN_MIN_MSGS", "3"))
# Archivo donde se cuenta cuantas sesiones ha tenido cada dominio candidato
DOMAIN_SESSIONS_COUNTER_FILE: Path = DATA_DIR / "domain_sessions_counter.json"

# ---------------------------------------------------------------------------
# Crear directorios al importar
# ---------------------------------------------------------------------------
def _ensure_dirs() -> None:
    """Crea todos los directorios necesarios si no existen."""
    for d in (DATA_DIR, KNOWLEDGE_DIR, LOCK_DIR, HOOK_STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)

_ensure_dirs()
