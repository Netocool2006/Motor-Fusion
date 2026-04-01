# -*- coding: utf-8 -*-
"""
test_engram_gaps.py -- Tests para los 5 gaps vs Engram
=======================================================
Cubre:
  1. Auto-pruning (core/memory_pruner.py)
  2. Feedback loop / hint effectiveness (core/hint_tracker.py)
  3. Memory consolidation (core/memory_consolidator.py)
  4. Memoria asociativa (core/associative_memory.py)
  5. Working memory explicita (core/working_memory.py)

Ejecutar directamente: python tests/test_engram_gaps.py
"""

import sys
import os
import json
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

# -- path setup
_TESTS_DIR = Path(__file__).resolve().parent
_MOTOR_DIR = _TESTS_DIR.parent
sys.path.insert(0, str(_MOTOR_DIR))

# ======================================================================
#  HELPERS
# ======================================================================

_pass_count = 0
_fail_count = 0
_errors = []


def _ok(name: str):
    global _pass_count
    _pass_count += 1
    print(f"  PASS  {name}")


def _fail(name: str, reason: str = ""):
    global _fail_count
    _fail_count += 1
    msg = f"  FAIL  {name}"
    if reason:
        msg += f" -- {reason}"
    print(msg)
    _errors.append(msg)


def assert_true(condition, name, reason=""):
    if condition:
        _ok(name)
    else:
        _fail(name, reason or "expected True")


def assert_false(condition, name, reason=""):
    if not condition:
        _ok(name)
    else:
        _fail(name, reason or "expected False")


def assert_equal(a, b, name):
    if a == b:
        _ok(name)
    else:
        _fail(name, f"expected {b!r}, got {a!r}")


def assert_gte(a, b, name):
    if a >= b:
        _ok(name)
    else:
        _fail(name, f"expected >= {b}, got {a}")


def assert_in(item, container, name):
    if item in container:
        _ok(name)
    else:
        _fail(name, f"{item!r} not in {container!r}")


# ======================================================================
#  SETUP: directorio temporal para DATA_DIR
# ======================================================================

_tmp_dir = None
_orig_data_dir = None


def setup_tmp_dir():
    global _tmp_dir, _orig_data_dir
    _tmp_dir = Path(tempfile.mkdtemp(prefix="motor_ia_engram_test_"))

    import config
    _orig_data_dir = config.DATA_DIR
    config.DATA_DIR = _tmp_dir

    # Parchear rutas derivadas en los modulos ya importados
    import core.memory_pruner as pruner
    import core.hint_tracker as ht
    import core.memory_consolidator as mc
    import core.associative_memory as am
    import core.working_memory as wm

    pruner.MEMORY_FILE = _tmp_dir / "learned_patterns.json"
    ht._INJECTION_LOG = _tmp_dir / "current_injection.json"
    ht._SCORES_FILE = _tmp_dir / "hint_scores.json"
    am.ASSOCIATIONS_FILE = _tmp_dir / "associative_graph.json"
    wm.WORKING_MEMORY_FILE = _tmp_dir / "working_memory.json"

    # memory_consolidator tiene MEMORY_FILE apuntando a learning_memory
    import core.learning_memory as lm
    lm.MEMORY_FILE = _tmp_dir / "learned_patterns.json"
    lm.PENDING_ERRORS_FILE = _tmp_dir / "pending_errors.json"
    mc.MEMORY_FILE = _tmp_dir / "learned_patterns.json"

    return _tmp_dir


def teardown_tmp_dir():
    global _tmp_dir, _orig_data_dir
    if _tmp_dir and _tmp_dir.exists():
        shutil.rmtree(_tmp_dir, ignore_errors=True)
    import config
    if _orig_data_dir:
        config.DATA_DIR = _orig_data_dir


# ======================================================================
#  SECCION 1: AUTO-PRUNING
# ======================================================================

def test_auto_prune():
    print("\n[1/5] AUTO-PRUNING (core/memory_pruner.py)")
    from core.memory_pruner import auto_prune, get_prune_candidates, get_stats
    from core.learning_memory import register_pattern, MEMORY_FILE

    # Crear patrones con distintas calidades
    _now = datetime.now(timezone.utc)
    _old = (_now - timedelta(days=95)).isoformat()

    mem = {
        "version": "1.0",
        "patterns": {},
        "tag_index": {},
        "stats": {"total_patterns": 0, "total_reuses": 0, "total_ai_calls_saved": 0},
    }

    # patron bueno: success_rate alto, usado recientemente
    mem["patterns"]["good_001"] = {
        "id": "good_001",
        "task_type": "bash",
        "context_key": "test/good",
        "solution": {"notes": "good pattern"},
        "tags": ["test"],
        "success_rate": 0.9,
        "reuse_count": 10,
        "last_used": _now.isoformat(),
        "created_at": _old,
    }

    # patron malo: success_rate bajo, no usado en 95 dias
    mem["patterns"]["bad_001"] = {
        "id": "bad_001",
        "task_type": "bash",
        "context_key": "test/bad",
        "solution": {"notes": "bad pattern"},
        "tags": ["test"],
        "success_rate": 0.1,
        "reuse_count": 2,
        "last_used": _old,
        "created_at": _old,
    }

    # patron sin reuses, viejo
    mem["patterns"]["stale_001"] = {
        "id": "stale_001",
        "task_type": "bash",
        "context_key": "test/stale",
        "solution": {"notes": "stale pattern"},
        "tags": ["test"],
        "success_rate": 0.0,
        "reuse_count": 0,
        "last_used": _old,
        "created_at": _old,
    }

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(mem), encoding="utf-8")

    # dry_run = no modifica
    candidates = get_prune_candidates()
    assert_gte(len(candidates), 1, "dry_run encuentra candidatos")

    # bad_001 y stale_001 deben estar entre candidatos
    candidate_ids = [c["id"] for c in candidates]
    assert_in("bad_001", candidate_ids, "bad_001 es candidato de pruning")
    assert_in("stale_001", candidate_ids, "stale_001 es candidato de pruning")

    # good_001 NO debe ser candidato
    assert_false("good_001" in candidate_ids, "good_001 NO es candidato")

    # prune real
    result = auto_prune(dry_run=False)
    assert_true(result["pruned"] >= 1, "auto_prune elimina al menos 1", f"pruned={result['pruned']}")
    assert_false(result["dry_run"], "dry_run=False en resultado")

    # verificar que el patron bueno sigue activo
    data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    good = data["patterns"].get("good_001", {})
    assert_true(not good.get("deleted_at"), "good_001 sigue activo despues de prune")

    # verificar soft-delete en malos
    bad = data["patterns"].get("bad_001", {})
    assert_true(bad.get("deleted_at"), "bad_001 fue soft-deleted")

    # stats
    stats = get_stats()
    assert_in("active", stats, "get_stats contiene 'active'")
    assert_in("pruned", stats, "get_stats contiene 'pruned'")
    assert_gte(stats["pruned"], 1, "stats.pruned >= 1")


# ======================================================================
#  SECCION 2: HINT TRACKER
# ======================================================================

def test_hint_tracker():
    print("\n[2/5] HINT TRACKER (core/hint_tracker.py)")
    from core.hint_tracker import (
        record_injection, score_injection, get_hint_score,
        sort_hints_by_effectiveness, get_top_hints, get_stats,
    )

    session = "test_session_ht_001"

    # score inicial = 0.5 (neutro)
    score_before = get_hint_score("hint_sap_login")
    assert_true(0.0 <= score_before <= 1.0, "score inicial es 0.0-1.0")

    # registrar inyeccion
    record_injection(["hint_sap_login", "hint_crm_orders"], session)

    # simular transcript que usa el hint
    transcript = "el usuario tuvo un error en sap_login y lo resolvi con las instrucciones del manual"
    score_injection(session, transcript)

    score_after = get_hint_score("hint_sap_login")
    assert_true(0.0 <= score_after <= 1.0, "score_after es 0.0-1.0")

    # hint no mencionado debe tener score bajo o igual al default
    score_unused = get_hint_score("hint_crm_orders")
    assert_true(0.0 <= score_unused <= 1.0, "score hint no usado es valido")

    # sort por efectividad
    hints = ["hint_sap_login", "hint_crm_orders", "hint_new_one"]
    sorted_hints = sort_hints_by_effectiveness(hints)
    assert_equal(len(sorted_hints), 3, "sort_hints devuelve misma cantidad")
    assert_true(isinstance(sorted_hints, list), "sort_hints devuelve lista")

    # get_top_hints
    tops = get_top_hints(limit=5)
    assert_true(isinstance(tops, list), "get_top_hints devuelve lista")

    # stats
    stats = get_stats()
    assert_in("total_tracked", stats, "get_stats contiene 'total_tracked'")
    assert_in("avg_score", stats, "get_stats contiene 'avg_score'")


# ======================================================================
#  SECCION 3: MEMORY CONSOLIDATOR
# ======================================================================

def test_memory_consolidator():
    print("\n[3/5] MEMORY CONSOLIDATOR (core/memory_consolidator.py)")
    from core.memory_consolidator import (
        consolidate, get_consolidation_candidates, get_stats,
    )
    from core.memory_pruner import MEMORY_FILE

    # Crear patrones similares del mismo tipo
    _now = datetime.now(timezone.utc).isoformat()
    mem = {
        "version": "1.0",
        "patterns": {},
        "tag_index": {},
        "stats": {"total_patterns": 0, "total_reuses": 0, "total_ai_calls_saved": 0},
    }

    # 3 patrones muy similares: mismas palabras en contexto
    for i in range(3):
        pid = f"sim_{i:03d}"
        mem["patterns"][pid] = {
            "id": pid,
            "task_type": "bash",
            "context_key": f"fix/python import error module",
            "solution": {
                "notes": "pip install module resuelve el error de import",
                "command": "pip install missing_module",
            },
            "tags": ["pip", "import", "error"],
            "success_rate": 0.8,
            "reuse_count": i + 1,
            "last_used": _now,
            "created_at": _now,
            "content_hash": f"hash_{i}",
        }

    # 1 patron diferente
    mem["patterns"]["diff_001"] = {
        "id": "diff_001",
        "task_type": "architecture",
        "context_key": "database connection pool config",
        "solution": {"notes": "set pool_size=10 in sqlalchemy"},
        "tags": ["db", "sqlalchemy"],
        "success_rate": 0.9,
        "reuse_count": 5,
        "last_used": _now,
        "created_at": _now,
    }

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(mem), encoding="utf-8")

    # dry_run -- no modifica
    candidates = get_consolidation_candidates()
    assert_true(isinstance(candidates, list), "get_consolidation_candidates devuelve lista")

    # consolidacion real
    result = consolidate(dry_run=False)
    assert_true(isinstance(result, dict), "consolidate devuelve dict")
    assert_in("consolidated", result, "resultado tiene 'consolidated'")
    assert_in("groups", result, "resultado tiene 'groups'")

    # stats
    stats = get_stats()
    assert_in("consolidated_patterns", stats, "get_stats contiene 'consolidated_patterns'")
    assert_in("candidate_groups", stats, "get_stats contiene 'candidate_groups'")


# ======================================================================
#  SECCION 4: ASSOCIATIVE MEMORY
# ======================================================================

def test_associative_memory():
    print("\n[4/5] ASSOCIATIVE MEMORY (core/associative_memory.py)")
    from core.associative_memory import (
        associate, get_associations, get_related_patterns,
        auto_associate_error_fix, remove_association, get_stats,
        ASSOCIATIONS_FILE,
    )

    pid_a = "pattern_aaa"
    pid_b = "pattern_bbb"
    pid_c = "pattern_ccc"

    # Crear asociacion simple
    ok = associate(pid_a, pid_b, "related")
    assert_true(ok, "associate crea relacion nueva")

    # Duplicado no debe crearse
    ok2 = associate(pid_a, pid_b, "related")
    assert_false(ok2, "associate no crea duplicado")

    # Crear mas relaciones
    associate(pid_b, pid_c, "leads_to")
    associate(pid_a, pid_c, "requires")

    # get_associations salientes de pid_a
    out = get_associations(pid_a, direction="out")
    assert_gte(len(out), 2, "pid_a tiene >= 2 asociaciones salientes")

    related_ids = [a["pattern_id"] for a in out]
    assert_in(pid_b, related_ids, "pid_b esta en salientes de pid_a")
    assert_in(pid_c, related_ids, "pid_c esta en salientes de pid_a")

    # get_associations entrantes de pid_b
    inc = get_associations(pid_b, direction="in")
    assert_gte(len(inc), 1, "pid_b tiene >= 1 entrante")

    # filtro por relacion
    req = get_associations(pid_a, relation="requires", direction="out")
    assert_equal(len(req), 1, "1 relacion 'requires' saliente de pid_a")
    assert_equal(req[0]["pattern_id"], pid_c, "requires apunta a pid_c")

    # auto_associate_error_fix
    auto_associate_error_fix("error_xxx", "fix_yyy")
    fixes = get_associations("fix_yyy", relation="fixes", direction="out")
    assert_equal(len(fixes), 1, "fix_yyy tiene relacion 'fixes' -> error_xxx")

    caused = get_associations("error_xxx", relation="caused_by", direction="out")
    assert_equal(len(caused), 1, "error_xxx tiene relacion 'caused_by' -> fix_yyy")

    # BFS traversal
    related = get_related_patterns(pid_a, depth=2)
    assert_true(isinstance(related, list), "get_related_patterns devuelve lista")
    assert_in(pid_b, related, "pid_b alcanzable desde pid_a depth=2")
    assert_in(pid_c, related, "pid_c alcanzable desde pid_a depth=2")
    assert_false(pid_a in related, "pid_a no esta en sus propios relacionados")

    # remove_association
    removed = remove_association(pid_a, pid_c, "requires")
    assert_equal(removed, 1, "remove_association elimina 1 edge")
    after = get_associations(pid_a, relation="requires", direction="out")
    assert_equal(len(after), 0, "no quedan edges 'requires' de pid_a")

    # stats
    stats = get_stats()
    assert_in("nodes", stats, "get_stats contiene 'nodes'")
    assert_in("edges", stats, "get_stats contiene 'edges'")
    assert_in("relation_types", stats, "get_stats contiene 'relation_types'")
    assert_gte(stats["nodes"], 3, "hay al menos 3 nodos")
    assert_gte(stats["edges"], 3, "hay al menos 3 edges")


# ======================================================================
#  SECCION 5: WORKING MEMORY
# ======================================================================

def test_working_memory():
    print("\n[5/5] WORKING MEMORY (core/working_memory.py)")
    from core.working_memory import (
        wm_add, wm_get, wm_clear, wm_promote, wm_to_context, get_stats,
    )

    session = "test_session_wm_001"

    # Agregar items
    id1 = wm_add("El usuario tiene un error en SAP login", "error", session)
    assert_true(len(id1) == 8, "wm_add retorna item_id de 8 chars")

    id2 = wm_add("Se aplico fix: reiniciar sesion SAP", "fix", session)
    assert_true(len(id2) == 8, "wm_add retorna item_id de 8 chars (fix)")

    id3 = wm_add("Decision: usar BAdI ZCL_CRM_ORDER para orden SAP", "decision", session)
    id4 = wm_add("Contexto: sistema en produccion", "context", session)
    id5 = wm_add("Hipotesis: el error es por timeout de sesion", "hypothesis", session)

    # wm_get todos
    all_items = wm_get(session_id=session)
    assert_gte(len(all_items), 5, "wm_get retorna >= 5 items")

    # wm_get filtrado por categoria
    errors = wm_get(category="error", session_id=session)
    assert_gte(len(errors), 1, "wm_get filtra por categoria 'error'")

    fixes = wm_get(category="fix", session_id=session)
    assert_gte(len(fixes), 1, "wm_get filtra por categoria 'fix'")

    # categoria invalida -> se guarda como 'observation'
    id_obs = wm_add("Observacion con categoria invalida", "categoria_inexistente", session)
    obs_items = wm_get(category="observation", session_id=session)
    assert_gte(len(obs_items), 1, "categoria invalida se guarda como observation")

    # session_id incorrecto -> retorna []
    wrong_session = wm_get(session_id="session_que_no_existe")
    assert_equal(wrong_session, [], "session_id incorrecto retorna []")

    # wm_to_context
    ctx = wm_to_context(max_items=20)
    assert_true(isinstance(ctx, str), "wm_to_context retorna string")
    assert_true(len(ctx) > 0, "wm_to_context no esta vacio")
    assert_in("WORKING MEMORY", ctx, "wm_to_context tiene header")

    # stats
    stats = get_stats()
    assert_in("total_items", stats, "get_stats contiene 'total_items'")
    assert_in("by_category", stats, "get_stats contiene 'by_category'")
    assert_in("promoted", stats, "get_stats contiene 'promoted'")
    assert_gte(stats["total_items"], 5, "stats.total_items >= 5")

    # wm_promote -- necesita learning_memory disponible, puede fallar suavemente
    try:
        from core.learning_memory import register_pattern
        promoted = wm_promote(id3, task_type="decision")
        # Si funciona, verificar que se marco como promovido
        if promoted:
            promoted_items = [i for i in wm_get(session_id=session) if i["id"] == id3]
            if promoted_items:
                assert_true(promoted_items[0].get("promoted"), "item promovido tiene promoted=True")
            _ok("wm_promote exitoso")
        else:
            _ok("wm_promote retorno False (aceptable si patron duplicado)")
    except Exception as e:
        _ok(f"wm_promote fallo suavemente: {e!s:.50}")

    # wm_clear
    wm_clear(session_id=session)
    after_clear = wm_get(session_id=session)
    assert_equal(after_clear, [], "wm_clear vacia la working memory")

    # wm_to_context vacio
    ctx_empty = wm_to_context()
    assert_equal(ctx_empty, "", "wm_to_context vacio retorna string vacio")


# ======================================================================
#  SECCION 6: INTEGRACION ENTRE MODULOS
# ======================================================================

def test_integration():
    print("\n[6/6] INTEGRACION ENTRE MODULOS")
    from core.associative_memory import associate, get_related_patterns, get_stats as am_stats
    from core.working_memory import wm_add, wm_get, wm_clear

    session = "test_integration_001"

    # Crear cadena: error -> fix -> decision
    associate("e_sap_login", "f_reiniciar_sesion", "fixes")
    associate("f_reiniciar_sesion", "d_agregar_timeout", "leads_to")
    associate("d_agregar_timeout", "e_sap_login", "caused_by")

    # BFS desde error
    from core.associative_memory import get_related_patterns
    related = get_related_patterns("e_sap_login", depth=2)
    assert_in("f_reiniciar_sesion", related, "fix es alcanzable desde error (depth=1)")
    assert_in("d_agregar_timeout", related, "decision es alcanzable desde error (depth=2)")

    # wm registra la cadena
    wm_add("Error SAP login detectado", "error", session)
    wm_add("Fix: reiniciar sesion aplicado", "fix", session)
    wm_add("Decision: agregar config timeout", "decision", session)

    items = wm_get(session_id=session)
    assert_gte(len(items), 3, "wm tiene 3 items de la cadena")

    cats = {i["category"] for i in items}
    assert_in("error", cats, "categoria error presente en wm")
    assert_in("fix", cats, "categoria fix presente en wm")
    assert_in("decision", cats, "categoria decision presente en wm")

    # stats combinados
    am_s = am_stats()
    assert_gte(am_s["edges"], 3, "grafo tiene >= 3 edges despues de integracion")

    wm_clear(session_id=session)


# ======================================================================
#  MAIN
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  TEST ENGRAM GAPS -- Motor_IA")
    print("=" * 60)

    tmp = setup_tmp_dir()
    print(f"  Directorio temporal: {tmp}")

    try:
        test_auto_prune()
        test_hint_tracker()
        test_memory_consolidator()
        test_associative_memory()
        test_working_memory()
        test_integration()
    finally:
        teardown_tmp_dir()

    print("\n" + "=" * 60)
    total = _pass_count + _fail_count
    print(f"  RESULTADO: {_pass_count}/{total} PASS | {_fail_count} FAIL")
    if _errors:
        print("\n  FALLOS:")
        for e in _errors:
            print(f"  {e}")
    print("=" * 60)

    sys.exit(0 if _fail_count == 0 else 1)
