# Motor_IA v2.3 (Motor Fusion IA)

Motor de aprendizaje adaptativo con pipeline RAG híbrido (KB → Internet → ML) que se conecta a cualquier CLI de IA (Claude Code, Gemini CLI, Ollama, etc.) y acumula conocimiento cross-sesión.

## Arquitectura

```
Motor_IA/
├── config.py                     # Paths centralizados (env vars, portabilidad)
├── mcp_kb_server.py              # MCP server (6 tools: buscar_kb, buscar_internet, etc.)
├── core/
│   ├── knowledge_base.py         # KB multi-dominio (IDF + decay temporal)
│   ├── vector_kb.py              # ChromaDB vector store (embeddings)
│   ├── web_search.py             # Búsqueda web (DuckDuckGo, optimize_query, relevancia)
│   ├── token_budget.py           # Compresión de contexto / ahorro de tokens
│   ├── learning_memory.py        # Motor fusionado de aprendizaje
│   ├── file_lock.py              # Lock cross-platform
│   ├── episodic_index.py         # Memoria cross-sesión
│   ├── sap_playbook.py           # Playbook SAP CRM
│   ├── domain_detector.py        # Detección automática de dominio
│   ├── disk_scanner.py           # Escaneo de carpetas para ingesta masiva
│   └── file_extractor.py         # Extracción de texto de archivos
├── hooks/
│   ├── motor_ia_hook.py          # Pre-hook (UserPromptSubmit) - pipeline KB→Internet→ML
│   ├── motor_ia_post_hook.py     # Post-hook (Stop) - auto-save aprendizajes
│   └── session_start.py          # SessionStart - inyección de contexto
├── dashboard/
│   ├── server.py                 # HTTP server (status, ingesta masiva, métricas)
│   └── index.html                # UI web (monitor, token budget, ChromaDB, ingesta)
├── adapters/
│   ├── base_adapter.py           # Interfaz genérica
│   ├── claude_code.py            # Adaptador Claude Code CLI
│   ├── gemini.py                 # Adaptador Gemini CLI
│   └── ollama.py                 # Adaptador Ollama
├── knowledge/                    # KB local multi-dominio (70+ dominios)
├── installer/
│   ├── setup.py                  # Instalador multi-OS, multi-CLI
│   ├── installer_gui.py          # Instalador visual (tkinter)
│   ├── manual_usuario.html       # Manual de usuario
│   └── offline_install.py        # Instalación offline
└── tests/
    ├── regression_test.py        # Tests de regresión
    ├── test_1000_pipeline_real.py # 1000 casos reales del pipeline
    └── test_50_mega.py           # 50 mega-tests
```

## Pipeline RAG Híbrido

```
Usuario → Hook (UserPromptSubmit) → Pipeline 3 pasos:
  1. KB Local (ChromaDB + TF-IDF)  → kb_pct%
  2. Internet (DuckDuckGo)          → internet_pct%
  3. ML (razonamiento LLM)          → ml_pct%
  → Respuesta combinada (kb + internet + ml = 100%)
```

## MCP Server (6 herramientas)

| Herramienta | Descripción |
|---|---|
| `buscar_kb` | Busca en Knowledge Base local (ChromaDB + JSON) |
| `buscar_internet` | Busca en DuckDuckGo con query optimizada |
| `guardar_aprendizaje` | Guarda patrones/hechos nuevos al KB |
| `listar_patrones` | Lista patrones aprendidos por dominio |
| `registrar_error_resuelto` | Registra error + solución |
| `estadisticas` | Métricas del sistema |

## Setup rápido

```bash
# 1. Instalar para Claude Code CLI (hooks + MCP + permisos)
python installer/setup.py --cli claude

# 2. Instalar para todos los CLIs + MCP server
python installer/setup.py --cli all --mcp

# 3. Iniciar dashboard (monitor web)
python dashboard/server.py
# → Abrir http://127.0.0.1:8080
```

## Dashboard

Monitor web en tiempo real que muestra:
- Estado de ChromaDB, hooks, Knowledge Base
- Métricas del día (queries, cache hits, web searches)
- Token Budget (tokens ahorrados por compresión)
- Ingesta Masiva (escanear carpetas → crear dominios → ingerir al KB)
- Log en tiempo real

## Variables de entorno (portabilidad)

| Variable | Descripción | Default |
|---|---|---|
| `CLAUDE_CODE_DIR` | Directorio de Claude Code | `~/.claude` |
| `CLAUDE_PROJECTS_DIR` | Directorio de proyectos | `~/.claude/projects` |
| `DASHBOARD_PORT` | Puerto del dashboard | `8080` |
| `DASHBOARD_HOST` | Host del dashboard | `127.0.0.1` |
| `HOOKS_IA_API_PORT` | Puerto API REST del KB | `7071` |
| `HOOKS_IA_API_HOST` | Host API REST del KB | `127.0.0.1` |
| `MOTOR_IA_DATA` | Directorio de datos | `~/.adaptive_cli` |

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
| Claude Code CLI | `adapters/claude_code.py` | Producción |
| Gemini CLI | `adapters/gemini.py` | Producción |
| Ollama | `adapters/ollama.py` | Producción |
| Claude Desktop (MCP) | `mcp_kb_server.py` | Producción |
| Cursor, OpenCode | `adapters/base_adapter.py` | Extensible |

Para agregar un CLI nuevo: heredar de `BaseAdapter` e implementar `inject_context()`, `capture_action()`, y `save_session()`.
