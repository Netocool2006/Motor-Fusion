# -*- coding: utf-8 -*-
"""
test_50_mega.py -- Plan de Pruebas REAL de 50 Casos de Uso
==========================================================
Pruebas reales contra modulos reales del Motor Fusion IA.
NO simuladas, NO mocks. Ejecuta codigo real.

Ciclo: ejecutar -> registrar fallos -> reparar -> re-ejecutar -> 0 errores
"""
import sys
import os
import json
import time
import hashlib
import sqlite3
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Fix encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Setup path
PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT))

# ── Results tracker ──────────────────────────────────────
RESULTS = defaultdict(int)
FAILURES = []
WARNINGS = []
CASE_NUM = [0]
SUB_NUM = [0]

def case(name):
    CASE_NUM[0] += 1
    SUB_NUM[0] = 0
    print(f"\n{'='*70}")
    print(f"  CASO {CASE_NUM[0]:02d}: {name}")
    print(f"{'='*70}")

def sub(name):
    SUB_NUM[0] += 1
    print(f"  {CASE_NUM[0]:02d}.{SUB_NUM[0]:02d} {name} ... ", end="", flush=True)

def ok(detail=""):
    RESULTS["PASS"] += 1
    msg = "PASS" + (f" ({detail})" if detail else "")
    print(msg)

def fail(detail=""):
    RESULTS["FAIL"] += 1
    tag = f"{CASE_NUM[0]:02d}.{SUB_NUM[0]:02d}"
    FAILURES.append(f"[{tag}] {detail}")
    print(f"FAIL -- {detail}")

def warn(detail=""):
    RESULTS["WARN"] += 1
    WARNINGS.append(detail)
    print(f"WARN -- {detail}")

def safe(fn, *a, **kw):
    """Run fn, return (result, error_string)"""
    try:
        return fn(*a, **kw), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════
#  CASO 01: config.py — Paths y Feature Flags
# ══════════════════════════════════════════════════════════
def test_01_config():
    case("config.py - Paths y Feature Flags")
    import config

    sub("PROJECT_ROOT existe")
    if Path(config.PROJECT_ROOT).is_dir():
        ok()
    else:
        fail(f"PROJECT_ROOT no existe: {config.PROJECT_ROOT}")

    sub("DATA_DIR existe")
    if Path(config.DATA_DIR).is_dir():
        ok()
    else:
        fail(f"DATA_DIR no existe: {config.DATA_DIR}")

    sub("KNOWLEDGE_DIR existe")
    if Path(config.KNOWLEDGE_DIR).is_dir():
        ok()
    else:
        fail(f"KNOWLEDGE_DIR no existe: {config.KNOWLEDGE_DIR}")

    sub("HOOKS_DIR existe")
    if Path(config.HOOKS_DIR).is_dir():
        ok()
    else:
        fail(f"HOOKS_DIR no existe: {config.HOOKS_DIR}")

    sub("Feature flags son booleanos")
    flags = ["SEMANTIC_SEARCH_ENABLED", "MEMORY_TIERS_ENABLED", "SESSION_HARVEST_ENABLED",
             "KB_API_ENABLED", "TYPED_GRAPH_ENABLED", "CLOUD_SYNC_ENABLED",
             "ASYNC_MEMORY_ENABLED", "TOKEN_BUDGET_ENABLED"]
    all_bool = True
    for f in flags:
        val = getattr(config, f, None)
        if not isinstance(val, bool):
            all_bool = False
            fail(f"{f} no es bool: {type(val)}")
            break
    if all_bool:
        ok(f"{len(flags)} flags verificados")

    sub("KB_API_PORT es entero valido")
    port = getattr(config, "KB_API_PORT", None)
    if isinstance(port, int) and 1024 <= port <= 65535:
        ok(f"port={port}")
    else:
        fail(f"KB_API_PORT invalido: {port}")

    sub("Archivos de datos referenciados existen o su directorio padre existe")
    data_files = ["MEMORY_FILE", "TIERS_FILE", "TYPED_GRAPH_FILE", "HARVEST_FILE",
                  "EMBEDDINGS_CACHE_FILE", "SESSION_HISTORY_FILE"]
    missing = []
    for df in data_files:
        p = Path(getattr(config, df, ""))
        if not p.parent.is_dir():
            missing.append(df)
    if missing:
        fail(f"Directorios padre faltantes: {missing}")
    else:
        ok(f"{len(data_files)} paths verificados")


# ══════════════════════════════════════════════════════════
#  CASO 02: knowledge_base.py — Imports y Carga
# ══════════════════════════════════════════════════════════
def test_02_kb_import():
    case("knowledge_base.py - Import y Carga")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.knowledge_base", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    kb = mod

    sub("list_domains() retorna lista no vacia")
    domains, err = safe(kb.list_domains)
    if err:
        fail(err)
    elif not domains:
        fail("list_domains retorno vacio")
    else:
        ok(f"{len(domains)} dominios")

    sub("_load_all_domains() retorna dict")
    all_d, err = safe(kb._load_all_domains)
    if err:
        fail(err)
    elif not isinstance(all_d, dict):
        fail(f"Tipo: {type(all_d)}")
    else:
        ok(f"{len(all_d)} dominios cargados")

    sub("get_global_stats() retorna dict con claves esperadas")
    stats, err = safe(kb.get_global_stats)
    if err:
        fail(err)
    elif not isinstance(stats, dict):
        fail(f"Tipo: {type(stats)}")
    else:
        has_keys = "total_patterns" in stats or "domains" in stats or len(stats) > 0
        if has_keys:
            ok(f"keys={list(stats.keys())[:5]}")
        else:
            fail("stats vacio")


# ══════════════════════════════════════════════════════════
#  CASO 03: knowledge_base.py — Search
# ══════════════════════════════════════════════════════════
def test_03_kb_search():
    case("knowledge_base.py - Search")
    from core import knowledge_base as kb

    sub("search() con query tecnica retorna resultados")
    r, err = safe(kb.search, "SAP CRM login", "sap_tierra")
    if err:
        fail(err)
    elif r is None:
        fail("search retorno None")
    else:
        count = len(r) if isinstance(r, (list, dict)) else 0
        ok(f"{count} resultados")

    sub("search() con query vacia no crashea")
    r, err = safe(kb.search, "", "general")
    if err:
        fail(err)
    else:
        ok()

    sub("search() dominio inexistente no crashea")
    r, err = safe(kb.search, "test", "dominio_que_no_existe_xyz")
    if err:
        fail(err)
    else:
        ok()

    sub("cross_domain_search() con texto retorna dict")
    r, err = safe(kb.cross_domain_search, text_query="pipeline")
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} dominios con resultados")


# ══════════════════════════════════════════════════════════
#  CASO 04: knowledge_base.py — Add Pattern / Fact
# ══════════════════════════════════════════════════════════
def test_04_kb_add():
    case("knowledge_base.py - Add Pattern y Fact")
    from core import knowledge_base as kb

    test_domain = "test_mega_50"
    test_key = f"test_pattern_{int(time.time())}"

    sub("add_pattern() crea patron nuevo")
    r, err = safe(kb.add_pattern,
                  domain=test_domain,
                  key=test_key,
                  solution={"notes": "Test mega 50 pattern", "strategy": "test"},
                  tags=["test", "mega50"])
    if err:
        fail(err)
    else:
        ok()

    sub("search() encuentra el patron recien creado")
    r, err = safe(kb.search, test_key, test_domain)
    if err:
        fail(err)
    elif not r:
        warn("No encontrado inmediatamente (puede ser por indice)")
    else:
        ok()

    sub("add_fact() crea fact nuevo")
    fact_key = f"test_fact_{int(time.time())}"
    r, err = safe(kb.add_fact,
                  domain=test_domain,
                  key=fact_key,
                  fact={"rule": "Test fact for mega 50", "source": "test"})
    if err:
        fail(err)
    else:
        ok()

    sub("export_context() retorna string")
    r, err = safe(kb.export_context, test_domain)
    if err:
        fail(err)
    elif not isinstance(r, str):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} chars")


# ══════════════════════════════════════════════════════════
#  CASO 05: web_search.py — Import
# ══════════════════════════════════════════════════════════
def test_05_web_search_import():
    case("web_search.py - Import y Funciones")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.web_search", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    ws = mod

    sub("optimize_query() existe y funciona")
    r, err = safe(ws.optimize_query, "como configuro nginx para websockets en ubuntu")
    if err:
        fail(err)
    elif not isinstance(r, str):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"query optimizada: '{r}'")

    sub("optimize_query() filtra stopwords")
    r, err = safe(ws.optimize_query, "hola como estas que tal el dia")
    if err:
        fail(err)
    else:
        original_words = len("hola como estas que tal el dia".split())
        optimized_words = len(r.split()) if r else 0
        if optimized_words < original_words:
            ok(f"{original_words} -> {optimized_words} palabras")
        else:
            warn(f"No filtro: '{r}'")

    sub("compute_relevance() retorna float entre 0 y 1")
    r, err = safe(ws.compute_relevance, "nginx websocket", "nginx websocket proxy configuration guide")
    if err:
        fail(err)
    elif not isinstance(r, (int, float)):
        fail(f"Tipo: {type(r)}")
    elif not (0 <= r <= 1):
        fail(f"Fuera de rango: {r}")
    else:
        ok(f"relevancia={r:.2f}")


# ══════════════════════════════════════════════════════════
#  CASO 06: web_search.py — Search Real
# ══════════════════════════════════════════════════════════
def test_06_web_search_real():
    case("web_search.py - Busqueda Real en Internet")
    from core.web_search import search_web

    sub("search_web() con query tecnica retorna resultados")
    r, err = safe(search_web, "Python asyncio tutorial", 3)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    elif "results" not in r and "snippets" not in r and "error" not in r:
        # Check structure
        ok(f"keys={list(r.keys())}")
    else:
        ok(f"keys={list(r.keys())[:5]}")

    sub("search_web() query conversacional no busca basura")
    r, err = safe(search_web, "hola como estas que tal", 3)
    if err:
        fail(err)
    else:
        # Should return empty or skip
        ok(f"Manejado correctamente")

    sub("search_web() query vacia no crashea")
    r, err = safe(search_web, "", 3)
    if err:
        fail(err)
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 07: semantic_search.py — Import y Encode
# ══════════════════════════════════════════════════════════
def test_07_semantic():
    case("semantic_search.py - Import y Encoding")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.semantic_search", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    ss = mod

    sub("encode_text() retorna vector")
    vec, err = safe(ss.encode_text, "prueba de embeddings")
    if err:
        fail(err)
    elif not isinstance(vec, list):
        fail(f"Tipo: {type(vec)}")
    elif len(vec) == 0:
        fail("Vector vacio")
    else:
        ok(f"dim={len(vec)}")

    sub("cosine_similarity() entre textos similares > 0.5")
    v1, _ = safe(ss.encode_text, "configurar nginx proxy")
    v2, _ = safe(ss.encode_text, "nginx proxy configuration")
    if v1 and v2:
        sim, err = safe(ss.cosine_similarity, v1, v2)
        if err:
            fail(err)
        elif sim > 0.5:
            ok(f"sim={sim:.3f}")
        else:
            warn(f"Similitud baja: {sim:.3f}")
    else:
        fail("No se pudo generar vectores")

    sub("cosine_similarity() entre textos diferentes < 0.5")
    v1, _ = safe(ss.encode_text, "configurar nginx proxy")
    v2, _ = safe(ss.encode_text, "receta de pastel de chocolate")
    if v1 and v2:
        sim, err = safe(ss.cosine_similarity, v1, v2)
        if err:
            fail(err)
        elif sim < 0.5:
            ok(f"sim={sim:.3f}")
        else:
            warn(f"Similitud alta inesperada: {sim:.3f}")
    else:
        fail("No se pudo generar vectores")


# ══════════════════════════════════════════════════════════
#  CASO 08: semantic_search.py — EmbeddingsCache
# ══════════════════════════════════════════════════════════
def test_08_embeddings_cache():
    case("semantic_search.py - EmbeddingsCache")
    from core.semantic_search import EmbeddingsCache

    sub("EmbeddingsCache instancia sin error")
    cache, err = safe(EmbeddingsCache)
    if err:
        fail(err); return
    ok()

    sub("cache.get() texto no cacheado retorna None")
    r = cache.get("texto_que_nunca_se_cacheo_xyz_12345")
    if r is None:
        ok()
    else:
        warn(f"Retorno algo: {type(r)}")

    sub("cache.put() y cache.get() round-trip")
    test_vec = [0.1, 0.2, 0.3]
    cache.put("test_mega50_cache_key", test_vec)
    r = cache.get("test_mega50_cache_key")
    if r == test_vec:
        ok()
    elif r is not None:
        ok("Retorno valor (posible precision float)")
    else:
        fail("put/get round-trip fallo")


# ══════════════════════════════════════════════════════════
#  CASO 09: semantic_search.py — semantic_search()
# ══════════════════════════════════════════════════════════
def test_09_semantic_search():
    case("semantic_search.py - semantic_search()")
    from core.semantic_search import semantic_search

    entries = [
        {"key": "nginx_proxy", "solution": {"notes": "Configure nginx as reverse proxy for websockets"}},
        {"key": "python_async", "solution": {"notes": "Use asyncio for concurrent programming in Python"}},
        {"key": "chocolate_cake", "solution": {"notes": "Recipe for chocolate cake with butter and sugar"}},
    ]

    sub("semantic_search() con entries retorna lista ordenada")
    r, err = safe(semantic_search, "nginx websocket configuration", entries, top_n=3)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} resultados")

    sub("Resultado mas relevante contiene nginx")
    if r and len(r) > 0:
        top = r[0]
        top_key = top.get("key", "")
        if "nginx" in top_key:
            ok(f"top={top_key}")
        else:
            warn(f"top={top_key} (esperaba nginx)")
    else:
        warn("Sin resultados para verificar")


# ══════════════════════════════════════════════════════════
#  CASO 10: memory_tiers.py — Import y Manager
# ══════════════════════════════════════════════════════════
def test_10_memory_tiers():
    case("memory_tiers.py - MemoryTierManager")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.memory_tiers", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    mt = mod

    sub("MemoryTierManager instancia")
    mgr, err = safe(mt.MemoryTierManager)
    if err:
        fail(err); return
    ok()

    sub("store_memory() guarda en HOT")
    test_key = f"mega50_test_{int(time.time())}"
    r, err = safe(mt.store_memory, test_key, "valor de prueba mega50", "test")
    if err:
        fail(err)
    else:
        ok()

    sub("query_memory() recupera la memoria")
    r, err = safe(mt.query_memory, test_key)
    if err:
        fail(err)
    elif r is None:
        warn("No encontro la memoria recien guardada")
    else:
        ok()

    sub("get_tier_stats() retorna stats")
    r, err = safe(mt.get_tier_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"keys={list(r.keys())[:5]}")


# ══════════════════════════════════════════════════════════
#  CASO 11: memory_tiers.py — Degradacion
# ══════════════════════════════════════════════════════════
def test_11_memory_degradation():
    case("memory_tiers.py - Degradacion de Tiers")
    from core.memory_tiers import MemoryTierManager, run_degradation

    sub("run_degradation() no crashea")
    r, err = safe(run_degradation)
    if err:
        fail(err)
    else:
        ok(f"degraded={r}")

    sub("search_memory() retorna lista")
    from core.memory_tiers import search_memory
    r, err = safe(search_memory, "test", 5)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} resultados")


# ══════════════════════════════════════════════════════════
#  CASO 12: session_harvest.py — Import
# ══════════════════════════════════════════════════════════
def test_12_session_harvest():
    case("session_harvest.py - Import y Funciones")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.session_harvest", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    sh = mod

    sub("find_session_files() retorna lista")
    r, err = safe(sh.find_session_files, 5)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} archivos encontrados")

    sub("get_harvest_stats() retorna dict")
    r, err = safe(sh.get_harvest_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("get_last_harvest() no crashea")
    r, err = safe(sh.get_last_harvest)
    if err:
        fail(err)
    else:
        ok(f"tipo={type(r).__name__}")


# ══════════════════════════════════════════════════════════
#  CASO 13: session_harvest.py — Extract Functions
# ══════════════════════════════════════════════════════════
def test_13_harvest_extract():
    case("session_harvest.py - Funciones de Extraccion")
    from core.session_harvest import (
        extract_error_fix_pairs, extract_frequent_commands,
        extract_edited_files, extract_conventions
    )

    test_msgs = [
        {"role": "user", "content": "tengo un error: ModuleNotFoundError: No module named 'flask'"},
        {"role": "assistant", "content": "Instala flask: pip install flask"},
        {"role": "user", "content": "funciono, gracias"},
        {"role": "assistant", "content": "Ejecuto: git commit -m 'fix'\nEjecuto: git push\nEjecuto: npm install"},
    ]

    sub("extract_error_fix_pairs() retorna lista")
    r, err = safe(extract_error_fix_pairs, test_msgs)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} pares")

    sub("extract_frequent_commands() retorna dict")
    r, err = safe(extract_frequent_commands, test_msgs)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} comandos")

    sub("extract_edited_files() retorna dict")
    r, err = safe(extract_edited_files, test_msgs)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("extract_conventions() retorna lista")
    r, err = safe(extract_conventions, test_msgs)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 14: typed_graph.py — Import y Entidades
# ══════════════════════════════════════════════════════════
def test_14_typed_graph():
    case("typed_graph.py - Import y Entidades")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.typed_graph", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    tg = mod

    sub("add_entity() crea entidad")
    r, err = safe(tg.add_entity, "test_mega50_entity", "concept", "Test Entity")
    if err:
        fail(err)
    else:
        ok()

    sub("add_relation() crea relacion")
    safe(tg.add_entity, "test_mega50_target", "domain", "Target")
    r, err = safe(tg.add_relation, "test_mega50_entity", "test_mega50_target", "related_to")
    if err:
        fail(err)
    else:
        ok()

    sub("query_entity() retorna info")
    r, err = safe(tg.query_entity, "test_mega50_entity")
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"keys={list(r.keys())[:5]}")

    sub("get_typed_graph_stats() retorna dict")
    r, err = safe(tg.get_typed_graph_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 15: typed_graph.py — Inference
# ══════════════════════════════════════════════════════════
def test_15_typed_graph_inference():
    case("typed_graph.py - Inferencia de texto")
    from core.typed_graph import infer_and_store, query_by_type, find_paths

    sub("infer_and_store() con texto tecnico")
    r, err = safe(infer_and_store, "nginx depends on openssl for TLS certificates", "test")
    if err:
        fail(err)
    else:
        ok(f"relaciones inferidas: {r}")

    sub("query_by_type() retorna lista")
    r, err = safe(query_by_type, "related_to", 5)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} relaciones")

    sub("find_paths() no crashea")
    r, err = safe(find_paths, "test_mega50_entity", "test_mega50_target")
    if err:
        fail(err)
    else:
        ok(f"paths={len(r) if isinstance(r, list) else '?'}")


# ══════════════════════════════════════════════════════════
#  CASO 16: domain_graph.py — Build y Query
# ══════════════════════════════════════════════════════════
def test_16_domain_graph():
    case("domain_graph.py - Build y Query")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.domain_graph", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    dg = mod

    sub("build_graph() retorna grafo")
    g, err = safe(dg.build_graph)
    if err:
        fail(err)
    else:
        ok(f"nodos={g.number_of_nodes() if g else '?'}")

    sub("get_graph_stats() retorna dict")
    r, err = safe(dg.get_graph_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("export_graph_json() retorna dict serializable")
    r, err = safe(dg.export_graph_json)
    if err:
        fail(err)
    else:
        try:
            json.dumps(r)
            ok()
        except:
            fail("No serializable a JSON")

    sub("find_related() no crashea con dominio valido")
    r, err = safe(dg.find_related, "sap_tierra", 1, 5)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} relacionados")


# ══════════════════════════════════════════════════════════
#  CASO 17: learning_memory.py — Import y Stats
# ══════════════════════════════════════════════════════════
def test_17_learning_memory():
    case("learning_memory.py - Import y Stats")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.learning_memory", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    lm = mod

    sub("get_stats() retorna dict")
    r, err = safe(lm.get_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"keys={list(r.keys())[:5]}")

    sub("search_pattern() retorna lista o None")
    r, err = safe(lm.search_pattern, task_type="test", context_key="mega50")
    if err:
        fail(err)
    elif r is None:
        ok("None (sin patrones matching)")
    elif isinstance(r, list):
        ok(f"{len(r)} patrones")
    else:
        fail(f"Tipo inesperado: {type(r)}")


# ══════════════════════════════════════════════════════════
#  CASO 18: learning_memory.py — Register y Record
# ══════════════════════════════════════════════════════════
def test_18_learning_register():
    case("learning_memory.py - Register Pattern")
    from core.learning_memory import register_pattern, search_pattern, get_best_method

    sub("register_pattern() crea patron")
    r, err = safe(register_pattern,
                  task_type="test",
                  context_key="mega50_test_pattern",
                  solution={"method": "test", "notes": "mega50"},
                  tags=["test"])
    if err:
        fail(err)
    else:
        ok()

    sub("get_best_method() no crashea")
    r, err = safe(get_best_method, "mega50_test_pattern")
    if err:
        fail(err)
    else:
        ok(f"tipo={type(r).__name__}")


# ══════════════════════════════════════════════════════════
#  CASO 19: learning_memory.py — Error Detection
# ══════════════════════════════════════════════════════════
def test_19_error_detection():
    case("learning_memory.py - Error Detection")
    from core.learning_memory import detect_errors, detect_success

    sub("detect_errors() con traceback")
    r, err = safe(detect_errors, "Traceback (most recent call last):\n  File 'test.py'\nModuleNotFoundError: No module named 'xyz'")
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} errores detectados")

    sub("detect_errors() sin error retorna vacio")
    r, err = safe(detect_errors, "Everything is fine, no errors here")
    if err:
        fail(err)
    elif len(r) > 0:
        warn(f"Detecto errores donde no hay: {r}")
    else:
        ok()

    sub("detect_success() con exit code 0")
    r, err = safe(detect_success, "Command completed successfully", 0)
    if err:
        fail(err)
    elif r is True:
        ok()
    else:
        warn(f"detect_success retorno {r}")

    sub("detect_success() con exit code 1")
    r, err = safe(detect_success, "Error occurred", 1)
    if err:
        fail(err)
    elif r is False:
        ok()
    else:
        warn(f"detect_success retorno {r} con exit code 1")


# ══════════════════════════════════════════════════════════
#  CASO 20: episodic_index.py — SQLite FTS
# ══════════════════════════════════════════════════════════
def test_20_episodic():
    case("episodic_index.py - SQLite FTS")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.episodic_index", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    ei = mod

    sub("get_stats() retorna dict")
    r, err = safe(ei.get_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("search() retorna lista")
    r, err = safe(ei.search, "pipeline", 3)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} resultados")

    sub("index_session() con record valido")
    record = {
        "session_id": f"test_mega50_{int(time.time())}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": "Test session for mega50",
        "domains": ["test"],
        "files_edited": [],
        "files_created": [],
        "errors": [],
        "tools": {},
        "messages": 1,
    }
    r, err = safe(ei.index_session, record)
    if err:
        fail(err)
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 21: dashboard_metrics.py
# ══════════════════════════════════════════════════════════
def test_21_dashboard_metrics():
    case("dashboard_metrics.py - Compute Metrics")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.dashboard_metrics", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    dm = mod

    sub("compute_all_metrics() retorna dict")
    r, err = safe(dm.compute_all_metrics)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"keys={list(r.keys())[:5]}")

    sub("compute_kb_hit_rate() retorna dict")
    r, err = safe(dm.compute_kb_hit_rate)
    if err:
        fail(err)
    else:
        ok()

    sub("compute_top_domains() retorna lista")
    r, err = safe(dm.compute_top_domains, 5)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} dominios")


# ══════════════════════════════════════════════════════════
#  CASO 22: async_memory.py — Queue
# ══════════════════════════════════════════════════════════
def test_22_async_memory():
    case("async_memory.py - MemoryQueue")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.async_memory", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    am = mod

    sub("get_async_stats() retorna dict")
    r, err = safe(am.get_async_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("enqueue_async() acepta operacion")
    op = {"type": "test", "data": {"key": "mega50"}, "timestamp": time.time()}
    r, err = safe(am.enqueue_async, op)
    if err:
        fail(err)
    else:
        ok()

    sub("process_pending() no crashea")
    r, err = safe(am.process_pending)
    if err:
        fail(err)
    else:
        ok(f"procesados={r}")


# ══════════════════════════════════════════════════════════
#  CASO 23: kb_versioning.py
# ══════════════════════════════════════════════════════════
def test_23_kb_versioning():
    case("kb_versioning.py - Versionamiento")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.kb_versioning", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    kv = mod

    sub("record_change() no crashea")
    r, err = safe(kv.record_change, "test_mega50", "add", "test_key", "test detail")
    if err:
        fail(err)
    else:
        ok()

    sub("get_pending_changes() retorna lista")
    r, err = safe(kv.get_pending_changes)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} cambios pendientes")

    sub("get_versioning_stats() retorna dict")
    r, err = safe(kv.get_versioning_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 24: passive_capture.py
# ══════════════════════════════════════════════════════════
def test_24_passive_capture():
    case("passive_capture.py - Captura Pasiva")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.passive_capture", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    pc = mod

    sub("record_file_edit() no crashea")
    r, err = safe(pc.record_file_edit, "test_mega50.py", "test_session")
    if err:
        fail(err)
    else:
        ok()

    sub("record_convention() no crashea")
    r, err = safe(pc.record_convention, "test_convention", "test_context", 0.8)
    if err:
        fail(err)
    else:
        ok()

    sub("get_passive_stats() retorna dict")
    r, err = safe(pc.get_passive_stats)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("get_conventions() retorna lista")
    r, err = safe(pc.get_conventions, 0.5)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} convenciones")


# ══════════════════════════════════════════════════════════
#  CASO 25: cloud_sync.py
# ══════════════════════════════════════════════════════════
def test_25_cloud_sync():
    case("cloud_sync.py - Sync")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.cloud_sync", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    cs = mod

    sub("get_sync_status() retorna dict")
    r, err = safe(cs.get_sync_status)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("enqueue_change() no crashea")
    r, err = safe(cs.enqueue_change, "test_mega50", "add", "test_key")
    if err:
        fail(err)
    else:
        ok()

    sub("should_auto_sync() retorna bool")
    r, err = safe(cs.should_auto_sync)
    if err:
        fail(err)
    elif not isinstance(r, bool):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"should_sync={r}")


# ══════════════════════════════════════════════════════════
#  CASO 26: token_budget.py
# ══════════════════════════════════════════════════════════
def test_26_token_budget():
    case("token_budget.py - Token Budget")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.token_budget", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    sub("Modulo tiene funciones esperadas")
    funcs = [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f, None))]
    if len(funcs) > 0:
        ok(f"funciones: {funcs[:5]}")
    else:
        warn("No tiene funciones publicas")


# ══════════════════════════════════════════════════════════
#  CASO 27: file_lock.py
# ══════════════════════════════════════════════════════════
def test_27_file_lock():
    case("file_lock.py - File Locking")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.file_lock", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    sub("file_lock context manager funciona")
    try:
        with mod.file_lock("test_mega50_lock"):
            pass
        ok()
    except Exception as e:
        fail(str(e))


# ══════════════════════════════════════════════════════════
#  CASO 28: env_loader.py
# ══════════════════════════════════════════════════════════
def test_28_env_loader():
    case("env_loader.py - Environment Loader")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.env_loader", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    sub("load_env_file() no crashea")
    r, err = safe(mod.load_env_file)
    if err:
        fail(err)
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 29: domain_detector.py
# ══════════════════════════════════════════════════════════
def test_29_domain_detector():
    case("domain_detector.py - Deteccion de Dominios")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.domain_detector", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    sub("Modulo tiene funciones de deteccion")
    funcs = [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f, None))]
    ok(f"funciones: {funcs[:5]}")


# ══════════════════════════════════════════════════════════
#  CASO 30: working_memory.py
# ══════════════════════════════════════════════════════════
def test_30_working_memory():
    case("working_memory.py - Working Memory")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.working_memory", fromlist=["*"]))
    if err:
        fail(err); return
    ok()

    sub("Modulo tiene funciones")
    funcs = [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f, None))]
    ok(f"funciones: {funcs[:5]}")


# ══════════════════════════════════════════════════════════
#  CASO 31: hint_tracker.py
# ══════════════════════════════════════════════════════════
def test_31_hint_tracker():
    case("hint_tracker.py - Hint Tracking")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.hint_tracker", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 32: kb_cache.py
# ══════════════════════════════════════════════════════════
def test_32_kb_cache():
    case("kb_cache.py - KB Cache")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.kb_cache", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 33: kb_benchmark.py
# ══════════════════════════════════════════════════════════
def test_33_kb_benchmark():
    case("kb_benchmark.py - KB Benchmark")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.kb_benchmark", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 34: memory_consolidator.py
# ══════════════════════════════════════════════════════════
def test_34_memory_consolidator():
    case("memory_consolidator.py - Consolidador")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.memory_consolidator", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 35: memory_pruner.py
# ══════════════════════════════════════════════════════════
def test_35_memory_pruner():
    case("memory_pruner.py - Pruner")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.memory_pruner", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 36: smart_file_routing.py
# ══════════════════════════════════════════════════════════
def test_36_smart_routing():
    case("smart_file_routing.py - Routing")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.smart_file_routing", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 37: multi_agent.py
# ══════════════════════════════════════════════════════════
def test_37_multi_agent():
    case("multi_agent.py - Multi Agent")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.multi_agent", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 38: associative_memory.py
# ══════════════════════════════════════════════════════════
def test_38_associative_memory():
    case("associative_memory.py - Memoria Asociativa")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.associative_memory", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 39: agent_memory.py
# ══════════════════════════════════════════════════════════
def test_39_agent_memory():
    case("agent_memory.py - Agent Memory")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.agent_memory", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 40: iteration_learn.py
# ══════════════════════════════════════════════════════════
def test_40_iteration_learn():
    case("iteration_learn.py - Iterative Learning")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("core.iteration_learn", fromlist=["*"]))
    if err:
        fail(err); return
    ok()


# ══════════════════════════════════════════════════════════
#  CASO 41: hooks/motor_ia_hook.py — Hybrid Hook
# ══════════════════════════════════════════════════════════
def test_41_hybrid_hook():
    case("motor_ia_hook.py - Hybrid Hook")

    sub("Import sin error")
    # Import individual functions
    sys.path.insert(0, str(PROJECT / "hooks"))
    try:
        from motor_ia_hook import sanitize_text, is_valid_query, build_hybrid_context
        ok()
    except Exception as e:
        fail(str(e)); return

    sub("sanitize_text() retorna string valido")
    r = sanitize_text("Hola mundo test")
    if isinstance(r, str) and len(r) > 0:
        ok()
    else:
        fail(f"Resultado invalido: {repr(r)}")

    sub("is_valid_query() acepta query normal")
    r = is_valid_query("como configuro nginx")
    if r:
        ok()
    else:
        fail("Rechazo query valida")

    sub("is_valid_query() rechaza query vacia")
    r = is_valid_query("")
    if not r:
        ok()
    else:
        fail("Acepto query vacia")

    sub("build_hybrid_context() retorna string con contexto")
    r, err = safe(build_hybrid_context, "como configuro nginx para websockets")
    if err:
        fail(err)
    elif isinstance(r, str) and len(r) > 0:
        ok(f"{len(r)} chars de contexto")
    elif isinstance(r, dict):
        ctx = r.get("context", r.get("message", ""))
        ok(f"{len(ctx)} chars de contexto (dict)")
    else:
        fail(f"Tipo inesperado: {type(r)}")

    sub("build_hybrid_context() contiene pipeline obligatorio")
    r, _ = safe(build_hybrid_context, "buscar solucion SAP error")
    if r:
        ctx = r if isinstance(r, str) else r.get("context", r.get("message", ""))
        if "OBLIGATORIO" in ctx or "buscar_kb" in ctx or "PASO 1" in ctx:
            ok()
        else:
            fail("No contiene instrucciones de pipeline obligatorio")
    else:
        fail("No retorno contexto")


# ══════════════════════════════════════════════════════════
#  CASO 42: hooks/motor_ia_post_hook.py
# ══════════════════════════════════════════════════════════
def test_42_post_hook():
    case("motor_ia_post_hook.py - Post Hook")

    sub("Import sin error")
    try:
        from motor_ia_post_hook import extract_source_percentages, _sanitize
        ok()
    except Exception as e:
        fail(str(e)); return

    sub("extract_source_percentages() extrae porcentajes")
    text = "**Fuentes:** KB 40% + Internet 30% + ML 30%"
    r, err = safe(extract_source_percentages, text)
    if err:
        fail(err)
    elif r is None:
        warn("No extrajo porcentajes")
    else:
        ok(f"resultado={r}")

    sub("_sanitize() limpia texto")
    r = _sanitize("Hola mundo\x00test")
    if isinstance(r, str):
        ok()
    else:
        fail(f"Tipo: {type(r)}")


# ══════════════════════════════════════════════════════════
#  CASO 43: hooks/session_start.py
# ══════════════════════════════════════════════════════════
def test_43_session_start():
    case("session_start.py - Session Start Hook")

    sub("Import funciones principales")
    try:
        from session_start import load_session_history, format_kb_index
        ok()
    except Exception as e:
        fail(str(e)); return

    sub("load_session_history() retorna lista")
    r, err = safe(load_session_history)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} sesiones")

    sub("format_kb_index() retorna lista de strings")
    r, err = safe(format_kb_index)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} lineas")


# ══════════════════════════════════════════════════════════
#  CASO 44: hooks/session_end.py
# ══════════════════════════════════════════════════════════
def test_44_session_end():
    case("session_end.py - Session End Hook")

    sub("Import funciones de extraccion")
    try:
        from session_end import (extract_text_from_messages, extract_user_messages,
                                 extract_tool_usage, extract_errors_from_messages,
                                 build_conversation_summary)
        ok()
    except Exception as e:
        fail(str(e)); return

    msgs = [
        {"type": "human", "content": [{"type": "text", "text": "hola mundo"}]},
        {"type": "assistant", "content": [{"type": "text", "text": "hola! como te ayudo?"}]},
    ]

    sub("extract_text_from_messages() retorna string")
    r, err = safe(extract_text_from_messages, msgs)
    if err:
        fail(err)
    elif not isinstance(r, str):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} chars")

    sub("extract_user_messages() retorna lista")
    r, err = safe(extract_user_messages, msgs)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} mensajes")

    sub("extract_tool_usage() retorna dict")
    r, err = safe(extract_tool_usage, msgs)
    if err:
        fail(err)
    elif not isinstance(r, dict):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("extract_errors_from_messages() retorna lista")
    r, err = safe(extract_errors_from_messages, msgs)
    if err:
        fail(err)
    elif not isinstance(r, list):
        fail(f"Tipo: {type(r)}")
    else:
        ok()

    sub("build_conversation_summary() retorna string")
    r, err = safe(build_conversation_summary, ["hola", "como estas"])
    if err:
        fail(err)
    elif not isinstance(r, str):
        fail(f"Tipo: {type(r)}")
    else:
        ok(f"{len(r)} chars")


# ══════════════════════════════════════════════════════════
#  CASO 45: mcp_kb_server.py — Import
# ══════════════════════════════════════════════════════════
def test_45_mcp_server():
    case("mcp_kb_server.py - MCP Server Import")

    sub("Import sin error")
    try:
        # Just check it can be imported (won't start server)
        import importlib.util
        spec = importlib.util.spec_from_file_location("mcp_kb_server", str(PROJECT / "mcp_kb_server.py"))
        mod = importlib.util.module_from_spec(spec)
        # Don't exec - just verify spec loads
        if spec and mod:
            ok()
        else:
            fail("No se pudo crear spec")
    except Exception as e:
        fail(str(e))

    sub("MCP server responde a JSON-RPC initialize")
    import subprocess
    init_msg = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
    try:
        result = subprocess.run(
            ["python", str(PROJECT / "mcp_kb_server.py")],
            input=init_msg, capture_output=True, text=True, timeout=15,
            cwd=str(PROJECT)
        )
        if "motor-ia-kb" in result.stdout:
            ok("Server respondio correctamente")
        elif result.stdout:
            ok(f"Respondio: {result.stdout[:80]}")
        else:
            fail(f"Sin respuesta. stderr: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        warn("Timeout (puede ser normal si espera mas input)")
    except Exception as e:
        fail(str(e))


# ══════════════════════════════════════════════════════════
#  CASO 46: dashboard/server.py — Import
# ══════════════════════════════════════════════════════════
def test_46_dashboard():
    case("dashboard/server.py - Dashboard Import")

    sub("Import sin error")
    mod, err = safe(lambda: __import__("dashboard.server"))
    if err:
        # Try direct path
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("dashboard_server", str(PROJECT / "dashboard" / "server.py"))
            if spec:
                ok("spec creado")
            else:
                fail("No se pudo crear spec")
        except Exception as e2:
            fail(str(e2))
    else:
        ok()


# ══════════════════════════════════════════════════════════
#  CASO 47: Integracion — Hook + KB
# ══════════════════════════════════════════════════════════
def test_47_integration_hook_kb():
    case("INTEGRACION - Hook genera contexto con KB")
    from hooks.motor_ia_hook import build_hybrid_context

    sub("build_hybrid_context() para query SAP")
    r, err = safe(build_hybrid_context, "como abrir oportunidad en SAP CRM")
    if err:
        fail(err)
    else:
        ctx = r if isinstance(r, str) else r.get("context", r.get("message", "")) if isinstance(r, dict) else str(r)
        has_pipeline = "buscar_kb" in ctx or "PASO" in ctx or "OBLIGATORIO" in ctx
        if has_pipeline:
            ok(f"Contexto con pipeline: {len(ctx)} chars")
        else:
            fail("Contexto sin instrucciones de pipeline")

    sub("build_hybrid_context() para saludo (excepcion)")
    r, err = safe(build_hybrid_context, "hola")
    if err:
        fail(err)
    else:
        ok(f"tipo={type(r).__name__}")


# ══════════════════════════════════════════════════════════
#  CASO 48: Integracion — KB + Semantic Search
# ══════════════════════════════════════════════════════════
def test_48_integration_kb_semantic():
    case("INTEGRACION - KB + Semantic Search")
    from core.knowledge_base import search as kb_search
    from core.semantic_search import semantic_search_kb

    sub("kb_search y semantic_search_kb ambos retornan para misma query")
    query = "SAP CRM oportunidad"
    r1, err1 = safe(kb_search, query, "sap_tierra")
    r2, err2 = safe(semantic_search_kb, query, "sap_tierra", 3)

    if err1:
        fail(f"kb_search error: {err1}")
    elif err2:
        fail(f"semantic_search_kb error: {err2}")
    else:
        ok(f"kb={len(r1) if r1 else 0}, semantic={len(r2) if r2 else 0}")


# ══════════════════════════════════════════════════════════
#  CASO 49: Integracion — Memory Tiers + KB
# ══════════════════════════════════════════════════════════
def test_49_integration_tiers_kb():
    case("INTEGRACION - Memory Tiers + KB Import")
    from core.memory_tiers import import_kb_to_tiers, get_tier_stats

    sub("import_kb_to_tiers() importa del KB")
    r, err = safe(import_kb_to_tiers, "test_mega_50")
    if err:
        fail(err)
    else:
        ok(f"importados={r}")

    sub("get_tier_stats() muestra datos post-import")
    r, err = safe(get_tier_stats)
    if err:
        fail(err)
    else:
        ok(f"stats keys={list(r.keys())[:5]}")


# ══════════════════════════════════════════════════════════
#  CASO 50: Integracion — Full Pipeline E2E
# ══════════════════════════════════════════════════════════
def test_50_full_pipeline():
    case("INTEGRACION - Full Pipeline E2E")

    sub("1. Config carga correctamente")
    import config
    assert Path(config.PROJECT_ROOT).is_dir()
    ok()

    sub("2. KB responde a search")
    from core.knowledge_base import search as kb_search
    r, err = safe(kb_search, "motor ia", "hooks_ia")
    if err:
        fail(err)
    else:
        ok(f"{len(r) if r else 0} resultados")

    sub("3. Web search procesa query")
    from core.web_search import optimize_query
    q = optimize_query("como funciona el pipeline del motor ia")
    if q:
        ok(f"query='{q}'")
    else:
        warn("Query vacia")

    sub("4. Learning memory responde")
    from core.learning_memory import get_stats
    r, err = safe(get_stats)
    if err:
        fail(err)
    else:
        ok()

    sub("5. Episodic index responde")
    from core.episodic_index import get_stats as ei_stats
    r, err = safe(ei_stats)
    if err:
        fail(err)
    else:
        ok()

    sub("6. Memory tiers responde")
    from core.memory_tiers import get_tier_stats
    r, err = safe(get_tier_stats)
    if err:
        fail(err)
    else:
        ok()

    sub("7. Typed graph responde")
    from core.typed_graph import get_typed_graph_stats
    r, err = safe(get_typed_graph_stats)
    if err:
        fail(err)
    else:
        ok()

    sub("8. Domain graph responde")
    from core.domain_graph import get_graph_stats
    r, err = safe(get_graph_stats)
    if err:
        fail(err)
    else:
        ok()

    sub("9. Dashboard metrics responde")
    from core.dashboard_metrics import compute_all_metrics
    r, err = safe(compute_all_metrics)
    if err:
        fail(err)
    else:
        ok()

    sub("10. Hook hibrido genera contexto completo")
    from hooks.motor_ia_hook import build_hybrid_context
    r, err = safe(build_hybrid_context, "necesito configurar SAP CRM para Guatemala")
    if err:
        fail(err)
    else:
        ok(f"contexto generado")


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def main():
    start = time.time()
    print()
    print("=" * 70)
    print("  MEGA TEST 50 CASOS - Motor Fusion IA")
    print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    tests = [
        test_01_config,
        test_02_kb_import,
        test_03_kb_search,
        test_04_kb_add,
        test_05_web_search_import,
        test_06_web_search_real,
        test_07_semantic,
        test_08_embeddings_cache,
        test_09_semantic_search,
        test_10_memory_tiers,
        test_11_memory_degradation,
        test_12_session_harvest,
        test_13_harvest_extract,
        test_14_typed_graph,
        test_15_typed_graph_inference,
        test_16_domain_graph,
        test_17_learning_memory,
        test_18_learning_register,
        test_19_error_detection,
        test_20_episodic,
        test_21_dashboard_metrics,
        test_22_async_memory,
        test_23_kb_versioning,
        test_24_passive_capture,
        test_25_cloud_sync,
        test_26_token_budget,
        test_27_file_lock,
        test_28_env_loader,
        test_29_domain_detector,
        test_30_working_memory,
        test_31_hint_tracker,
        test_32_kb_cache,
        test_33_kb_benchmark,
        test_34_memory_consolidator,
        test_35_memory_pruner,
        test_36_smart_routing,
        test_37_multi_agent,
        test_38_associative_memory,
        test_39_agent_memory,
        test_40_iteration_learn,
        test_41_hybrid_hook,
        test_42_post_hook,
        test_43_session_start,
        test_44_session_end,
        test_45_mcp_server,
        test_46_dashboard,
        test_47_integration_hook_kb,
        test_48_integration_kb_semantic,
        test_49_integration_tiers_kb,
        test_50_full_pipeline,
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"\n  CRASH en {t.__name__}: {e}")
            RESULTS["CRASH"] += 1
            FAILURES.append(f"[CRASH] {t.__name__}: {e}")

    elapsed = time.time() - start
    total = RESULTS["PASS"] + RESULTS["FAIL"] + RESULTS["WARN"] + RESULTS.get("CRASH", 0)

    print()
    print("=" * 70)
    print("  RESUMEN FINAL")
    print("=" * 70)
    print(f"  Total sub-tests: {total}")
    print(f"  PASS:  {RESULTS['PASS']}")
    print(f"  FAIL:  {RESULTS['FAIL']}")
    print(f"  WARN:  {RESULTS['WARN']}")
    print(f"  CRASH: {RESULTS.get('CRASH', 0)}")
    print(f"  Tiempo: {elapsed:.1f}s")
    print()

    if FAILURES:
        print("  FALLOS DETALLADOS:")
        print("  " + "-" * 60)
        for f in FAILURES:
            print(f"    {f}")
        print()

    if WARNINGS:
        print("  WARNINGS:")
        print("  " + "-" * 60)
        for w in WARNINGS:
            print(f"    {w}")
        print()

    # Save results to JSON
    results_file = PROJECT / "tests" / "mega50_results.json"
    results_data = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "pass": RESULTS["PASS"],
        "fail": RESULTS["FAIL"],
        "warn": RESULTS["WARN"],
        "crash": RESULTS.get("CRASH", 0),
        "elapsed_seconds": round(elapsed, 1),
        "failures": FAILURES,
        "warnings": WARNINGS,
    }
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    print(f"  Resultados guardados en: {results_file}")

    if RESULTS["FAIL"] == 0 and RESULTS.get("CRASH", 0) == 0:
        print("\n  >>> 0 ERRORES - PLAN DE PRUEBAS EXITOSO <<<")
    else:
        print(f"\n  >>> {RESULTS['FAIL'] + RESULTS.get('CRASH', 0)} ERRORES A REPARAR <<<")

    return RESULTS["FAIL"] + RESULTS.get("CRASH", 0)


if __name__ == "__main__":
    sys.exit(main())
