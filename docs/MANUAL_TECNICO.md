# Motor Fusion IA - Manual Tecnico

**Version:** 1.0.2-fusion  
**Fecha:** Abril 2026  
**Arquitectura:** RAG Hibrido (ChromaDB + DuckDuckGo + ML)

---

## Tabla de Contenidos

1. [Arquitectura General](#1-arquitectura-general)
2. [Pipeline de Procesamiento](#2-pipeline-de-procesamiento)
3. [Modulos del Core](#3-modulos-del-core)
4. [Sistema de Hooks](#4-sistema-de-hooks)
5. [Base de Conocimiento (KB)](#5-base-de-conocimiento-kb)
6. [Motor Vectorial (ChromaDB)](#6-motor-vectorial-chromadb)
7. [Deteccion de Dominios](#7-deteccion-de-dominios)
8. [Sistema de Memoria](#8-sistema-de-memoria)
9. [Dashboard y API REST](#9-dashboard-y-api-rest)
10. [Ingesta de Datos](#10-ingesta-de-datos)
11. [Integraciones Externas](#11-integraciones-externas)
12. [Configuracion](#12-configuracion)
13. [Estructura de Archivos](#13-estructura-de-archivos)
14. [Seguridad y Concurrencia](#14-seguridad-y-concurrencia)
15. [Diagramas de Flujo](#15-diagramas-de-flujo)

---

## 1. Arquitectura General

Motor Fusion IA es un sistema RAG (Retrieval-Augmented Generation) que inyecta conocimiento contextual en las respuestas de Claude Code CLI. Opera como un pipeline de hooks que intercepta queries del usuario, busca en multiples fuentes de conocimiento, y enriquece el contexto de Claude.

### Diagrama de Componentes

```
+-------------------+     +-------------------+     +-------------------+
|   Claude Code     |     |   Motor Fusion    |     |   Fuentes de      |
|   CLI             |     |   IA (Hooks)      |     |   Conocimiento    |
|                   |     |                   |     |                   |
|  Usuario          |---->| motor_ia_hook.py  |---->| ChromaDB (vector) |
|  pregunta         |     | (pre-hook)        |     | knowledge/ (JSON) |
|                   |     |                   |     | DuckDuckGo (web)  |
|  Claude           |<----| build_context()   |<----| Session history   |
|  responde         |     |                   |     |                   |
|                   |---->| session_end.py    |---->| Episodic index    |
|  Sesion           |     | (post-hook)       |     | Learning memory   |
|  termina          |     |                   |     | Domain detector   |
+-------------------+     +-------------------+     +-------------------+
```

### Capas del Sistema

| Capa | Modulos | Responsabilidad |
|---|---|---|
| **Interfaz** | Hooks, Dashboard, TUI, MCP Server | Interaccion con usuario y Claude |
| **Orquestacion** | motor_ia_hook, session_start/end | Coordinacion del pipeline |
| **Busqueda** | vector_kb, knowledge_base, web_search | Retrieval de conocimiento |
| **Almacenamiento** | ChromaDB, JSON files, SQLite FTS5 | Persistencia de datos |
| **Aprendizaje** | learning_memory, domain_detector, episodic_index | Mejora continua |

---

## 2. Pipeline de Procesamiento

### Flujo Pre-Respuesta (UserPromptSubmit)

```
Usuario escribe query
        |
        v
motor_ia_hook.py (stdin: JSON)
        |
        +---> sanitize_text() -- Limpia surrogates/control chars
        +---> is_valid_query() -- Filtra basura (tags XML, queries cortas, /commands)
        |
        v
_check_session_continuity()
        |
        +---> Lee session_summary.json
        +---> Construye resumen de ultimas 20 interacciones
        |
        v
search_kb(query)
        |
        +---> vector_kb.ask_kb(query)
        +---> Embeds query con all-MiniLM-L6-v2 (384 dims)
        +---> Busca top-5 por similitud coseno en ChromaDB
        +---> Aplica scatter filter (sim < 0.55 + 3+ dominios dispersos = reject)
        +---> Retorna (kb_content, kb_pct)
        |
        v
Si kb_pct < 80%:
        |
        +---> search_internet(query)
        +---> web_search.search_web(query) via DuckDuckGo
        +---> Retorna (internet_content, internet_pct)
        |
        v
Normalizar: kb_pct + internet_pct + ml_pct = 100%
        |
        v
build_context()
        |
        +---> Construye XML: <motor_ia>
        +---> <fuentes_estimadas kb="X%" internet="Y%" ml="Z%" />
        +---> <session_anterior>...</session_anterior>
        +---> <kb_knowledge>...</kb_knowledge>
        +---> <internet_knowledge>...</internet_knowledge>
        +---> <instrucciones>...</instrucciones>
        +---> <reporte_fuentes>...</reporte_fuentes>
        |
        v
save_state() --> motor_ia_state.json
        |
        v
stdout: {"hookSpecificOutput": {"additionalContext": "<motor_ia>..."}}
        |
        v
Claude recibe el contexto inyectado y responde
```

### Flujo Post-Respuesta (Stop)

```
Claude termina de responder
        |
        v
motor_ia_post_hook.py (stdin: JSON con respuesta)
        |
        +---> Lee motor_ia_state.json (needs_save?)
        +---> extract_source_percentages() -- Parsea "KB X% + Internet Y% + ML Z%"
        |
        v
Si needs_save:
        +---> vector_kb.save_to_kb(query, response)
        +---> Genera doc_id: learned_{timestamp}
        +---> Almacena en ChromaDB con metadata
        |
        v
_update_session_summary(query, answer_preview)
        +---> Actualiza session_summary.json (max 20 interacciones)
```

### Flujo Fin de Sesion (Stop)

```
Sesion de Claude termina
        |
        v
session_end.py (stdin: JSON con transcript_path)
        |
        +---> read_transcript() -- Parsea JSONL completo
        +---> Extrae: mensajes, errores, archivos, comandos, decisiones
        |
        v
+---> Guarda en session_history.json
+---> Indexa en episodic_index.db (FTS5)
+---> domain_detector.detect_from_session(record)
+---> auto_promote_domain(domain, msg_count)
+---> auto_learn_from_session(domain, text)
+---> Actualiza domain_cooccurrence.json
+---> Actualiza domain_markov.json
+---> working_memory.clear(session_id)
```

---

## 3. Modulos del Core

### 3.1 vector_kb.py - Motor RAG Vectorial

**Ubicacion:** `core/vector_kb.py`  
**Stack:** sentence-transformers + ChromaDB  
**Modelo:** all-MiniLM-L6-v2 (384 dimensiones, similitud coseno)

#### API Publica

```python
def ask_kb(query: str) -> dict:
    """
    Busca conocimiento relevante en ChromaDB.
    Returns: {
        "answer": str,       # Texto consolidado de los mejores resultados
        "found": bool,       # True si hay resultados relevantes
        "source": str,       # "vector_kb" o "notebooklm"
        "similarity": float, # Mejor score de similitud
        "sources_used": int, # Cantidad de fuentes usadas
    }
    """

def save_to_kb(query: str, answer: str, source: str = "ML") -> str | None:
    """
    Guarda conocimiento nuevo en ChromaDB.
    Doc ID: learned_{timestamp}
    Returns: doc_id o None si fallo
    """

def index_knowledge_base() -> dict:
    """
    Indexa todos los archivos JSON de knowledge/ en ChromaDB.
    Returns: {"indexed": int, "skipped": int, "total": int}
    """

def get_stats() -> dict:
    """
    Estadisticas del KB vectorial.
    Returns: {"total": int, "facts": int, "patterns": int, "learned": int, "sessions": int}
    """

def save_session_summary(summary: str) -> str | None:
    """Guarda resumen de sesion. Doc ID: session_{timestamp}"""

def get_last_session() -> str | None:
    """Recupera ultimo resumen de sesion por timestamp."""
```

#### Algoritmo de Busqueda

1. Encode query con SentenceTransformer (384 dims)
2. Query ChromaDB: top-5 por similitud coseno
3. **Scatter filter:** Si best_sim < 0.55 Y hay 3+ dominios dispersos -> rechazar (falso positivo)
4. Filtrar resultados con similitud > 0.48
5. Consolidar top-3 en respuesta unica
6. Retornar con metadata

#### Esquema de Documentos en ChromaDB

```python
# Documento almacenado
{
    "id": "learned_1711920000",       # o "fact_sap_tierra_abc123"
    "document": "Pregunta: ...\nRespuesta: ...",
    "metadata": {
        "query": "texto original (max 200 chars)",
        "source": "ML|auto_learned|manual",
        "type": "learned|fact|pattern|session_summary",
        "domain": "auto_learned|sap_tierra|general|...",
        "timestamp": "2026-04-03 20:00:00",
    }
}
```

### 3.2 knowledge_base.py - KB Multi-Dominio

**Ubicacion:** `core/knowledge_base.py`  
**Almacenamiento:** Archivos JSON en `knowledge/`

#### Estructura en Disco

```
knowledge/
  domains.json                   # Registro de todos los dominios
  sap_tierra/
    patterns.json                # Soluciones, scripts, workarounds
    facts.json                   # Reglas, procesos, conocimiento declarativo
  outlook/
    patterns.json
  general/
    patterns.json
  ...
```

#### API Publica

```python
def add_pattern(domain: str, key: str, solution: dict,
                tags: list = None, error_context: dict = None) -> str:
    """
    Agrega un patron (solucion tecnica) al KB.
    solution = {
        "strategy": str,
        "code_snippet": str,
        "notes": str,
        "attempts_to_solve": int,
    }
    Returns: ID (12 hex chars del SHA-256)
    """

def add_fact(domain: str, key: str, fact: dict, tags: list = None) -> str:
    """
    Agrega un hecho (conocimiento declarativo) al KB.
    fact = {
        "rule": str,
        "applies_to": str,
        "examples": [{"input": str, "output": str, "context": str}],
        "exceptions": str,
        "source": str,
        "confidence": "verified|observed|inferred",
    }
    Returns: ID (12 hex chars)
    """

def search(domain: str, key: str = None, tags: list = None,
           text_query: str = None) -> list[dict]:
    """
    Busca en el KB de un dominio.
    Scoring: IDF * success_rate * exp(-0.01 * dias_sin_acceso)
    Returns: Lista rankeada de entradas
    """

def cross_domain_search(tags: list = None, text_query: str = None,
                        domains: list = None) -> dict:
    """Busca en multiples dominios. Returns: {domain: [entries]}"""

def export_context(domain: str = None, tags: list = None,
                   text_query: str = None, limit: int = 10) -> str:
    """Exporta KB formateado para inyeccion en prompt"""

def list_domains() -> list[str]:
    """Lista todos los dominios conocidos"""

def get_global_stats() -> dict:
    """Estadisticas globales: total_patterns, total_facts, domains"""
```

#### Formato de Entrada en patterns.json

```json
{
  "abc123def456": {
    "id": "abc123def456",
    "type": "pattern",
    "key": "read_excel_utf8",
    "solution": {
      "strategy": "Usar openpyxl con encoding forzado",
      "code_snippet": "wb = openpyxl.load_workbook('file.xlsx')",
      "notes": "Funciona con Excel 2010+",
      "attempts_to_solve": 2
    },
    "tags": ["excel", "encoding", "openpyxl"],
    "error_context": null,
    "created_at": "2026-04-01T10:00:00",
    "updated_at": "2026-04-03T15:30:00",
    "stats": {
      "lookups": 5,
      "reuses": 3,
      "success_rate": 1.0,
      "last_accessed": "2026-04-03T15:30:00",
      "access_count": 8
    }
  }
}
```

#### Operaciones Atomicas

Todas las escrituras usan el patron:
```python
tmp = path.with_suffix(".tmp")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
_atomic_replace(tmp, path)  # os.replace() - atomico en Windows/Linux
```

### 3.3 domain_detector.py - Clasificador de Dominios

**Ubicacion:** `core/domain_detector.py`

#### API Publica

```python
def detect(text: str) -> str:
    """Dominio dominante o 'general'. Threshold: AUTO_ASSIGN_THRESHOLD (0.7)"""

def suggest(text: str) -> list[str]:
    """Candidatos con score >= SUGGEST_THRESHOLD (0.4). Max 5."""

def detect_multi(text: str, max_domains: int = 3) -> list[str]:
    """Multiples dominios para tareas mixtas. Score >= 50% del max."""

def learn_domain_keywords(domain: str, new_keywords: list):
    """Expande keywords de un dominio en domains.json"""

def auto_promote_domain(domain: str, user_msg_count: int = 0) -> bool:
    """
    Auto-promueve un dominio despues de N sesiones.
    Requiere: AUTO_DOMAIN_MIN_SESSIONS (3) sesiones con AUTO_DOMAIN_MIN_MSGS (10) mensajes.
    Returns: True si fue promovido en esta llamada.
    """

def auto_learn_from_session(domain: str, text: str):
    """Extrae y aprende keywords de una sesion confirmada"""
```

#### Algoritmo de Scoring

```
1. Extraer keywords del texto (regex \b[a-zA-Z0-9_]{3,}\b, sin stop words, max 30)
2. Cargar keywords de cada dominio desde domains.json
3. Para cada dominio:
   - domain_keywords = keywords_almacenadas + nombre_dominio + variantes
   - score = |keywords_texto ∩ domain_keywords|  (interseccion)
4. Si max_score >= 0.7: retornar ese dominio
5. Sino: retornar "general"
```

#### Formato domains.json (Fusion)

```json
{
  "sap_tierra": {
    "description": "Knowledge domain: sap_tierra",
    "file": "patterns.json",
    "entry_type": "pattern",
    "num_entries": 354,
    "keywords": ["sap", "gui", "scripting", "abap", "tcode"]
  },
  "outlook": {
    "description": "Knowledge domain: outlook",
    "file": "patterns.json",
    "entry_type": "pattern",
    "num_entries": 141
  }
}
```

### 3.4 episodic_index.py - Memoria Episodica

**Ubicacion:** `core/episodic_index.py`  
**Almacenamiento:** SQLite con FTS5 (`core/data/episodic_index.db`)

```python
def index_session(session_id: str, domain: str, summary: str,
                  insights: list, files: list, errors: list):
    """Indexa una sesion completa para busqueda full-text"""

def search(query: str, domain: str = None, limit: int = 10) -> list[dict]:
    """Busqueda FTS5 con ranking por relevancia"""

def rebuild_from_history() -> int:
    """Reconstruye el indice desde session_history.json"""

def get_stats() -> dict:
    """Estadisticas: total_sessions, total_episodes, domains"""
```

### 3.5 file_extractor.py - Extractor de Archivos

**Ubicacion:** `core/file_extractor.py`

#### Formatos Soportados

| Categoria | Extensiones | Metodo de Lectura |
|---|---|---|
| Texto/Codigo | .txt .md .py .js .ts .java .go .rs .sql .json .yaml .xml .html .css (40+) | UTF-8 directo |
| Word | .docx | ZIP -> word/document.xml -> `<w:t>` elements |
| Excel | .xlsx | ZIP -> xl/sharedStrings.xml + worksheets/sheet1.xml |
| PowerPoint | .pptx | ZIP -> ppt/slides/slideN.xml -> `<a:t>` elements |
| PDF | .pdf | pypdf/PyPDF2 si disponible, fallback: regex sobre raw bytes |

#### Chunking

```python
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    Divide texto en chunks con solapamiento.
    Corta en limites de oracion (. ! ? \\n) dentro del ultimo 20% del chunk.
    """
```

### 3.6 web_search.py - Busqueda Web

**Ubicacion:** `core/web_search.py`  
**Motor:** DuckDuckGo (via `duckduckgo-search`)

```python
def search_web(query: str, max_results: int = 5) -> dict:
    """
    Returns: {
        "found": bool,
        "results": [{"title": str, "url": str, "body": str}],
        "summary": str,       # Top resultados concatenados
        "internet_pct": int,   # Cobertura estimada (0-100)
    }
    """
```

### 3.7 learning_memory.py - Memoria de Aprendizaje

**Ubicacion:** `core/learning_memory.py`  
**Almacenamiento:** `core/data/learning_memory.json`

Deduplicacion de 3 niveles:
1. **Topic key upsert:** Si ya existe un patron con el mismo key, actualizar
2. **Content hash:** Si el contenido es identico (SHA-256), rechazar
3. **Nuevo:** Crear patron nuevo

18 tipos validos de patron. 2 scopes: `project` y `personal`.

### 3.8 working_memory.py - Memoria de Trabajo

**Ubicacion:** `core/working_memory.py`  
**Almacenamiento:** `core/data/working_memory.json`

Memoria volatil con TTL. Se limpia al final de cada sesion.

```python
MAX_ITEMS = 50
TTL_HOURS = 24
```

### 3.9 disk_scanner.py - Escaner de Disco

**Ubicacion:** `core/disk_scanner.py`

```python
def scan(paths: list, depth: int = 3, min_files: int = 3) -> dict:
    """Descubre dominios candidatos en el filesystem"""

def scan_and_apply(paths, depth, min_files) -> dict:
    """Escanea y crea dominios en domains.json (confianza >= 0.5)"""

def scan_and_ingest(paths, depth, min_files, max_files_per_domain=50) -> dict:
    """Escanea, crea dominios Y alimenta el KB con contenido de archivos"""
```

#### Algoritmo de Confianza

```
confidence = (file_factor * 0.45) + (concentration * 0.35) + (ext_consistency * 0.20)

donde:
  file_factor = min(1.0, log(n_files + 1) / log(50))
  concentration = top3_keyword_freq / total_keyword_freq
  ext_consistency = 1.0 / (1.0 + (n_extensions - 1) * 0.15)
```

---

## 4. Sistema de Hooks

### Protocolo de Comunicacion

Los hooks se comunican con Claude Code via stdin/stdout usando JSON:

```
Claude Code --stdin--> Hook Script --stdout--> Claude Code
                (JSON input)         (JSON output)
```

### Hook: UserPromptSubmit (motor_ia_hook.py)

**Entrada (stdin):**
```json
{
  "prompt": "texto del usuario",
  "session_id": "uuid",
  "hook_event_name": "UserPromptSubmit",
  "cwd": "C:/proyecto"
}
```

**Salida (stdout):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "<motor_ia>...</motor_ia>"
  }
}
```

### Hook: Stop (session_end.py)

**Entrada (stdin):**
```json
{
  "session_id": "uuid",
  "transcript_path": "path/to/transcript.jsonl",
  "last_assistant_message": "...",
  "cwd": "C:/proyecto",
  "stop_hook_active": true
}
```

**Salida:** `{}` (sin output directo, guarda estado internamente)

### Hook: Stop (motor_ia_post_hook.py)

**Entrada (stdin):**
```json
{
  "last_assistant_message": "respuesta completa de Claude",
  "session_id": "uuid"
}
```

Lee `motor_ia_state.json` para saber si debe guardar conocimiento nuevo.

---

## 5. Base de Conocimiento (KB)

### Arquitectura de Almacenamiento

```
+------------------------+     +----------------------+
|    ChromaDB            |     |   knowledge/ (JSON)  |
|    (Busqueda primaria) |     |   (Respaldo/fuente)  |
|                        |     |                      |
|  - Vector similarity   |     |  - 22 dominios       |
|  - 300+ documentos     |     |  - patterns.json     |
|  - all-MiniLM-L6-v2   |     |  - facts.json        |
|  - Cosine distance     |     |  - IDF scoring       |
+------------------------+     +----------------------+
          |                              |
          v                              v
+------------------------+     +----------------------+
|    Episodic Index      |     |   Session Summary    |
|    (Memoria cruzada)   |     |   (Continuidad)      |
|                        |     |                      |
|  - SQLite FTS5         |     |  - Ultimas 20        |
|  - Busqueda full-text  |     |    interacciones     |
|  - Por sesion/dominio  |     |  - Auto-refresh      |
+------------------------+     +----------------------+
```

### Flujo de Datos del KB

1. **Ingreso:** Conocimiento entra via post-hook (auto-save), ingesta masiva, o manual
2. **Indexacion:** `index_knowledge_base()` lee JSON de `knowledge/` y vectoriza en ChromaDB
3. **Busqueda:** `ask_kb()` busca por similitud coseno en ChromaDB
4. **Aprendizaje:** `auto_learn_from_session()` expande keywords de dominios
5. **Limpieza:** `memory_pruner` elimina patrones con baja tasa de exito

### Tipos de Documentos

| Tipo | Fuente | Formato | Ejemplo |
|---|---|---|---|
| `fact` | knowledge/*.json | JSON estructurado | Regla de negocio SAP |
| `pattern` | knowledge/*.json | JSON estructurado | Script de automatizacion |
| `learned` | post-hook auto-save | Pregunta + Respuesta | Q&A de sesion |
| `session_summary` | session_end | Resumen de sesion | "Se trabajo en X, Y, Z" |

---

## 6. Motor Vectorial (ChromaDB)

### Configuracion

```python
# Modelo de embeddings
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# ChromaDB
COLLECTION_NAME = "motor_ia_kb"
DISTANCE_METRIC = "cosine"  # hnsw:space
PERSIST_DIR = "core/chroma_db/"

# Umbrales de busqueda
SIMILARITY_THRESHOLD = 0.48   # Minimo para retornar resultado
SCATTER_THRESHOLD = 0.55      # Debajo de esto + dominios dispersos = reject
TOP_K = 5                     # Resultados a recuperar
CONSOLIDATE_TOP = 3           # Resultados a consolidar en respuesta
```

### Scatter Filter (Anti Falso-Positivo)

```python
# Si la mejor similitud es baja Y los resultados vienen de 3+ dominios diferentes:
if best_sim < 0.55:
    domains_in_results = set(r["domain"] for r in results)
    if len(domains_in_results) >= 3:
        return {"found": False}  # Resultados dispersos = no relevante
```

---

## 7. Deteccion de Dominios

### Ciclo de Vida de un Dominio

```
Texto nuevo no encaja en ningun dominio
        |
        v
Se clasifica como "general"
        |
        v (sesion termina)
auto_promote_domain(): incrementa contador
        |
        v (3+ sesiones con 10+ mensajes cada una)
Dominio PROMOVIDO a domains.json
        |
        +---> Se crea entrada en domains.json
        +---> Se crea directorio en knowledge/
        +---> auto_learn_from_session() extrae keywords
        |
        v (uso continuado)
Keywords se expanden automaticamente
Confianza de deteccion mejora
```

### Stop Words (Filtradas)

85+ palabras comunes en espanol e ingles que se ignoran en la deteccion:
```
el, la, los, las, un, una, de, del, en, que, y, a, por, con, para,
the, an, in, of, to, is, it, for, and, or,
puedo, quiero, hacer, haz, dame, muestra, dime, necesito, ver...
```

---

## 8. Sistema de Memoria

### Capas de Memoria

| Capa | Persistencia | TTL | Uso |
|---|---|---|---|
| Working Memory | Archivo JSON | 24 horas | Contexto de sesion actual |
| Session Summary | Archivo JSON | Permanente (ultimas 20) | Continuidad entre sesiones |
| Learning Memory | Archivo JSON | Permanente (con pruning) | Patrones aprendidos |
| Episodic Index | SQLite FTS5 | Permanente | Busqueda cross-sesion |
| ChromaDB | Base vectorial | Permanente | Busqueda semantica |
| Knowledge Base | Archivos JSON | Permanente | Conocimiento estructurado |

### Auto-Pruning

```python
AUTO_PRUNE_ENABLED = True
AUTO_PRUNE_MIN_SUCCESS_RATE = 0.3    # Patrones con < 30% exito se eliminan
AUTO_PRUNE_DAYS_UNUSED = 30          # Patrones sin usar 30+ dias se eliminan
AUTO_PRUNE_MIN_REUSES = 2            # Minimo 2 reusos para sobrevivir
```

### Consolidacion

```python
CONSOLIDATION_ENABLED = True
CONSOLIDATION_MIN_PATTERNS = 3        # Minimo 3 patrones similares para fusionar
CONSOLIDATION_SIMILARITY_THRESHOLD = 0.8  # Similitud minima para considerar fusion
```

---

## 9. Dashboard y API REST

### Servidor

**Archivo:** `dashboard/server.py`  
**Framework:** Python stdlib `http.server.HTTPServer`  
**Puerto default:** 8080

### Endpoints

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/` | Dashboard HTML principal |
| `GET` | `/api/status` | Estado completo del sistema (JSON) |
| `GET` | `/api/ingest/status` | Progreso de ingesta en curso (JSON) |
| `POST` | `/api/ingest/start` | Iniciar ingesta masiva |
| `POST` | `/api/ingest/stop` | Detener ingesta en curso |

### POST /api/ingest/start

**Body:**
```json
{
  "path": "D:\\MisDocumentos",
  "depth": 3,
  "min_files": 3,
  "max_files_per_domain": 50
}
```

**Response:**
```json
{"status": "started", "path": "D:\\MisDocumentos"}
```

### GET /api/ingest/status

**Response:**
```json
{
  "running": true,
  "progress": 45,
  "message": "[3/8] Ingiriendo: sap_automation",
  "phase": "ingest",
  "domains_found": 8,
  "files_processed": 23,
  "facts_ingested": 156,
  "duplicates_skipped": 12,
  "started_at": "2026-04-03T20:00:00",
  "finished_at": null
}
```

### GET /api/status (Health Check)

**Response:**
```json
{
  "timestamp": "03-04-2026 20:00:00",
  "overall_health": "HEALTHY",
  "components_ok": 4,
  "components_total": 4,
  "chromadb": {
    "status": "OK",
    "total_docs": 300,
    "facts": 116,
    "patterns": 138,
    "learned": 45,
    "sessions": 1
  },
  "hooks": {
    "status": "OK",
    "pre_hook": "REGISTERED",
    "post_hook": "REGISTERED"
  },
  "knowledge_local": {
    "status": "OK",
    "domains": 22,
    "size_mb": 8.5
  },
  "metrics": {
    "queries_today": 15,
    "cache_hits": 3,
    "vector_hits": 12,
    "internet_searches": 4,
    "auto_saves": 8,
    "errors": 0
  }
}
```

### Health Scoring

```
HEALTHY:  4/4 componentes OK
DEGRADED: 2-3/4 componentes OK
CRITICAL: <2/4 componentes OK
```

---

## 10. Ingesta de Datos

### Pipeline de Ingesta Masiva

```
Path de usuario (ej: D:\)
        |
        v
disk_scanner.scan()
        |
        +---> Recorre carpetas (depth=3, skip: node_modules, .git, etc.)
        +---> Agrupa archivos por carpeta padre (cluster tematico)
        +---> Extrae keywords de nombres de archivo y contenido (500 chars)
        +---> Calcula confianza por cluster
        |
        v
Crear dominios (confianza >= 0.4)
        |
        +---> learn_domain_keywords(domain, keywords)
        +---> Crea entrada en domains.json
        +---> Crea directorio en knowledge/
        |
        v
Ingerir contenido (max 50 archivos/dominio)
        |
        +---> file_extractor.extract_text(file, max_chars=5000)
        +---> chunk_text(text, chunk_size=800, overlap=100)
        |
        v
Deduplicacion (por cada chunk)
        |
        +---> Encode chunk con all-MiniLM-L6-v2
        +---> Query ChromaDB: top-1 por similitud
        +---> Si distancia coseno < 0.08 (similitud > 92%): SKIP
        |
        v
Guardar en KB
        |
        +---> knowledge_base.add_fact(domain, key, fact, tags)
        |
        v
Indexar en ChromaDB
        |
        +---> vector_kb.index_knowledge_base()
```

### CLI de Ingesta

```bash
# Escanear y mostrar (sin guardar)
python core/disk_scanner.py scan D:\Proyectos

# Escanear y crear dominios (sin ingerir contenido)
python core/disk_scanner.py apply D:\Proyectos

# Escanear, crear dominios Y alimentar KB
python core/disk_scanner.py ingest D:\Proyectos

# Estimar tiempo de escaneo
python core/disk_scanner.py estimate D:\

# Ingesta con formato especifico
python ingest_knowledge.py D:\docs --domain mi_dominio --type fact --tags tag1,tag2
```

---

## 11. Integraciones Externas

### Claude Code CLI (Principal)
- **Integracion:** Via hooks en `settings.json`
- **Protocolo:** stdin/stdout JSON
- **Eventos:** UserPromptSubmit, Stop, PreToolUse

### Claude Desktop (MCP Server)
- **Archivo:** `mcp_kb_server.py`
- **Protocolo:** Model Context Protocol (stdio)
- **Herramientas expuestas:** buscar_kb, guardar_aprendizaje, listar_patrones, registrar_error_resuelto, estadisticas

### DuckDuckGo (Busqueda Web)
- **Modulo:** `core/web_search.py`
- **Libreria:** `duckduckgo-search`
- **Activacion:** Automatica cuando KB < 80%

### Adaptadores Multi-CLI
- **Claude Code:** `adapters/claude_code.py`
- **Gemini:** `adapters/gemini.py`
- **Ollama:** `adapters/ollama.py`

---

## 12. Configuracion

### Variables de Entorno

| Variable | Default | Descripcion |
|---|---|---|
| `DASHBOARD_PORT` | 8080 | Puerto del dashboard web |
| `DASHBOARD_HOST` | 127.0.0.1 | Host del dashboard |
| `CLAUDE_PROJECTS_DIR` | Auto-detectado | Override del directorio de proyectos Claude |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Endpoint de Ollama |
| `TOKENIZERS_PARALLELISM` | false | Desactiva warnings de tokenizers |

### Umbrales Configurables (config.py)

| Variable | Valor | Descripcion |
|---|---|---|
| `AUTO_ASSIGN_THRESHOLD` | 0.7 | Minimo para auto-asignar dominio |
| `SUGGEST_THRESHOLD` | 0.4 | Minimo para sugerir dominio |
| `AUTO_DOMAIN_MIN_SESSIONS` | 3 | Sesiones para auto-promover dominio |
| `AUTO_DOMAIN_MIN_MSGS` | 10 | Mensajes minimos por sesion |
| `CONFIDENCE_THRESHOLD` | 0.5 | Minimo para reusar patron |
| `WORKING_MEMORY_MAX_ITEMS` | 50 | Items maximos en working memory |
| `WORKING_MEMORY_TTL_HOURS` | 24 | TTL de working memory |
| `DEDUP_WINDOW_SECS` | 60 | Ventana de deduplicacion |
| `RECENT_HOURS` | 1 | Horas atras para sesiones recientes |
| `CONFIDENCE_DECAY_DAYS` | 30 | Dias para decay de confianza |
| `CONFIDENCE_DECAY_RATE` | 0.1 | Tasa de decay |
| `AUTO_PRUNE_MIN_SUCCESS_RATE` | 0.3 | Tasa minima para no podar |
| `AUTO_PRUNE_DAYS_UNUSED` | 30 | Dias sin uso para podar |

---

## 13. Estructura de Archivos

```
C:\Hooks_IA/
|
|-- config.py                    # Configuracion centralizada
|-- __init__.py                  # Package marker
|-- mcp_kb_server.py             # MCP server para Claude Desktop
|-- ingest_knowledge.py          # CLI de ingesta
|-- requirements.txt             # Dependencias pip
|
|-- core/                        # Modulos principales
|   |-- vector_kb.py             # RAG: ChromaDB + embeddings
|   |-- knowledge_base.py        # KB multi-dominio (JSON)
|   |-- domain_detector.py       # Clasificador de dominios
|   |-- learning_memory.py       # Aprendizaje de patrones
|   |-- episodic_index.py        # Memoria episodica (SQLite FTS5)
|   |-- working_memory.py        # Memoria de trabajo (volatil)
|   |-- associative_memory.py    # Grafo asociativo
|   |-- file_extractor.py        # Lector multi-formato
|   |-- disk_scanner.py          # Escaner de filesystem
|   |-- web_search.py            # Busqueda DuckDuckGo
|   |-- tui.py                   # Terminal UI (rich)
|   |-- http_api.py              # API REST
|   |-- sap_playbook.py          # Playbooks SAP
|   |-- memory_pruner.py         # Auto-limpieza de patrones
|   |-- memory_consolidator.py   # Fusion de patrones similares
|   |-- hint_tracker.py          # Efectividad de hints
|   |-- file_lock.py             # Locks de archivo
|   |-- timezone_utils.py        # Utilidades de tiempo
|   |-- env_loader.py            # Carga de .env
|   |
|   |-- chroma_db/               # Base de datos vectorial
|   |   |-- chroma.sqlite3
|   |   |-- <uuid>/data_level0.bin, header.bin, ...
|   |
|   |-- data/                    # Datos de runtime
|       |-- session_history.json
|       |-- episodic_index.db
|       |-- learning_memory.json
|       |-- working_memory.json
|       |-- execution_log.json
|       |-- domain_sessions_counter.json
|
|-- hooks/                       # Scripts de hook
|   |-- motor_ia_hook.py         # Pre-respuesta (KB + Internet)
|   |-- motor_ia_post_hook.py    # Post-respuesta (auto-save)
|   |-- session_start.py         # Inicio de sesion
|   |-- session_end.py           # Fin de sesion (aprendizaje)
|
|-- knowledge/                   # Base de conocimiento (JSON)
|   |-- domains.json             # Registro de dominios
|   |-- sap_tierra/patterns.json
|   |-- outlook/patterns.json
|   |-- business_rules/patterns.json
|   |-- ... (22 dominios)
|
|-- dashboard/                   # Dashboard web
|   |-- server.py                # HTTP server + API
|   |-- index.html               # Frontend (HTML/CSS/JS)
|
|-- adapters/                    # Adaptadores multi-CLI
|   |-- base_adapter.py
|   |-- claude_code.py
|   |-- gemini.py
|   |-- ollama.py
|
|-- installer/                   # Instaladores
|   |-- offline_install.py       # Instalador offline
|   |-- build_offline_package.py # Generador de paquete
|   |-- installer_gui.py         # Instalador GUI (tkinter)
|   |-- setup.py                 # Instalador legacy
|   |-- manual_usuario.html      # Manual HTML
|   |-- bundle/
|       |-- python_win/          # Python embebido
|       |-- get-pip.py           # Bootstrap de pip
|
|-- tests/                       # Tests
|   |-- regression_test.py
|
|-- docs/                        # Documentacion
    |-- MANUAL_INSTALACION.md
    |-- MANUAL_TECNICO.md
```

---

## 14. Seguridad y Concurrencia

### File Locking

```python
# core/file_lock.py
@contextmanager
def file_lock(name: str, timeout: int = 10):
    """
    Lock basado en archivos para operaciones concurrentes.
    Crea archivo .lock en core/locks/.
    Timeout de 10 segundos por default.
    """
```

Todos los accesos a archivos JSON compartidos (domains.json, patterns.json, etc.) usan locks:
```python
with file_lock(f"kb_{domain}"):
    data = _load_domain(domain)
    data[entry_id] = new_entry
    _save_domain(domain, data)
```

### Sanitizacion de Input

```python
def sanitize_text(text):
    """Elimina surrogates y caracteres de control que crashean utf-8."""
    return text.encode("utf-8", errors="replace").decode("utf-8")
```

### Validacion de Queries

```python
def is_valid_query(query):
    """Filtra queries invalidas: < 5 chars, /commands, XML tags del sistema."""
```

### Limites de Archivos

| Limite | Valor | Modulo |
|---|---|---|
| Max file size para extraccion | 10 MB | file_extractor.py |
| Max chars por extraccion | 5,000 chars | file_extractor.py |
| Max archivos por dominio (ingesta) | 50 | disk_scanner.py |
| Max keywords del texto | 30 | domain_detector.py |
| Max interacciones en session_summary | 20 | motor_ia_post_hook.py |
| Max lineas en execution_log | 5,000 | knowledge_base.py |

---

## 15. Diagramas de Flujo

### Flujo Completo de una Query

```
[Usuario]
    |
    | "Como configuro SAP GUI Scripting?"
    v
[Claude Code CLI]
    |
    | stdin: {"prompt": "Como configuro SAP GUI Scripting?"}
    v
[motor_ia_hook.py] -----> [session_summary.json]
    |                              |
    | "Sesion anterior: ..."       |
    v                              |
[vector_kb.ask_kb()] <----- [ChromaDB]
    |                         384-dim vectors
    | kb_pct = 65%            cosine similarity
    v
[web_search.search_web()] <----- [DuckDuckGo]
    |
    | internet_pct = 25%
    v
[build_context()]
    |
    | kb=65% + internet=25% + ml=10%
    | <motor_ia> XML con conocimiento real
    v
[Claude Code CLI]
    |
    | Claude genera respuesta usando contexto inyectado
    v
[motor_ia_post_hook.py]
    |
    | Extrae "**Fuentes:** KB 65% + Internet 25% + ML 10%"
    | needs_save = True (ML > 0)
    v
[vector_kb.save_to_kb()] ----> [ChromaDB]
    |                           Nuevo doc: learned_1711920000
    v
[session_summary.json] (interaccion #N guardada)
    |
    v
[Sesion termina]
    |
    v
[session_end.py]
    |
    +---> session_history.json
    +---> episodic_index.db (FTS5)
    +---> domain_detector.auto_learn("sap_tierra", keywords)
    +---> domain_cooccurrence.json
```
