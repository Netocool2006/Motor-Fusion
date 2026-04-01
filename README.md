# Motor-Fusion (Motor_IA Unificado)

Motor de aprendizaje adaptativo que se conecta a cualquier CLI de IA (Claude Code, Gemini CLI, Ollama, etc.) y acumula conocimiento cross-sesion.

Resultado de fusionar Motor 1 (Asistente IA - features, KB, 160+ patrones) con Motor 2 (Motor Inteligente - arquitectura limpia, file_lock, atomic_replace).

## Arquitectura

```
Motor_IA/
├── config.py                     # Paths centralizados, resolucion de data dir
├── core/
│   ├── learning_memory.py        # Motor fusionado de aprendizaje
│   ├── knowledge_base.py         # KB multi-dominio (IDF + decay temporal)
│   ├── file_lock.py              # Lock cross-platform
│   ├── episodic_index.py         # Memoria cross-sesion
│   ├── sap_playbook.py           # Playbook SAP CRM
│   └── domain_detector.py        # Deteccion automatica de dominio
├── adapters/
│   ├── base_adapter.py           # Interfaz generica (inject_context, capture_action, save_session)
│   ├── claude_code.py            # Adaptador Claude Code CLI (hooks stdin/stdout)
│   ├── gemini.py                 # Adaptador Gemini CLI
│   └── ollama.py                 # Adaptador Ollama
├── hooks/                        # Hooks genericos por evento
│   ├── on_session_start.py
│   ├── on_user_message.py
│   ├── on_tool_use.py
│   ├── on_session_end.py
│   └── on_error.py
├── mcp_server.py                 # MCP server (Claude Desktop y otros)
├── sync_to_github.py             # Sync datos -> repo GitHub privado
├── restore_from_github.py        # Restore datos desde repo GitHub
├── installer/
│   └── setup.py                  # Instalador multi-OS, multi-CLI
└── tests/
```

Datos en `~/.adaptive_cli/` (configurable via env `MOTOR_IA_DATA`):

```
~/.adaptive_cli/
├── learned_patterns.json         # Patrones aprendidos
├── knowledge/                    # 13+ dominios de conocimiento
│   ├── sow.json
│   ├── bom.json
│   ├── sap_tierra.json
│   └── ...
├── episodic_index.db             # Indice de memoria episodica
├── sap_playbook.db               # Playbook SAP CRM
├── session_history.json          # Historial de sesiones
└── execution_log.jsonl           # Log de ejecuciones
```

## Setup rapido

```bash
# 1. Instalar para Claude Code CLI
python installer/setup.py --cli claude

# 2. Instalar para todos los CLIs + MCP server
python installer/setup.py --cli all --mcp

# 3. Solo Gemini CLI
python installer/setup.py --cli gemini
```

## GitHub Sync (respaldo cross-PC)

```bash
# Sincronizar datos a repo privado
python sync_to_github.py --repo ~/adaptive-cli-data

# Restaurar en PC nueva
python restore_from_github.py --repo https://github.com/USER/adaptive-cli-data.git
```

## Adaptadores soportados

| CLI | Adaptador | Estado |
|-----|-----------|--------|
| Claude Code CLI | `adapters/claude_code.py` | Produccion |
| Gemini CLI | `adapters/gemini.py` | Produccion |
| Ollama | `adapters/ollama.py` | Produccion |
| Claude Desktop (MCP) | `mcp_server.py` | Produccion |
| Cursor, OpenCode | `adapters/base_adapter.py` | Extensible |

Para agregar un CLI nuevo: heredar de `BaseAdapter` e implementar `inject_context()`, `capture_action()`, y `save_session()`.
