# -*- coding: utf-8 -*-
"""
associative_memory.py -- Grafo de relaciones entre patrones
============================================================
Extiende Motor_IA con un grafo ligero de asociaciones entre patrones
de learning_memory, knowledge_base y SAP playbook.

Tipos de relacion:
  caused_by  -- este error fue causado por ese patron
  fixes      -- este patron resuelve ese error/problema
  requires   -- este patron requiere que ese otro este activo
  leads_to   -- usar este patron tipicamente lleva a necesitar ese otro
  related    -- relacion general de similaridad o co-ocurrencia
  supersedes -- este patron reemplaza a ese otro (post-consolidacion)

Auto-deteccion:
  La correlacion error->fix existente en learning_memory se registra
  automaticamente como caused_by/fixes via auto_associate_error_fix().

Motor_IA ventaja sobre Engram:
  Engram usa grafos de embedding. Nosotros usamos grafos semanticos
  expliciticos (el agente decide las relaciones) + auto-deteccion
  de error->fix desde la correlacion ya existente. Sin dependencias externas.

Storage: DATA_DIR/associative_graph.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR
from core.file_lock import file_lock, _atomic_replace

ASSOCIATIONS_FILE = DATA_DIR / "associative_graph.json"

VALID_RELATIONS = frozenset({
    "caused_by", "fixes", "requires", "leads_to", "related", "supersedes"
})


# -- I/O -----------------------------------------------------------------------

def _load_graph() -> dict:
    if ASSOCIATIONS_FILE.exists():
        try:
            return json.loads(ASSOCIATIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"nodes": {}, "edges": []}


def _save_graph(graph: dict):
    ASSOCIATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ASSOCIATIONS_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _atomic_replace(tmp, ASSOCIATIONS_FILE)


# -- API publica ---------------------------------------------------------------

def associate(pattern_id_a: str, pattern_id_b: str,
              relation: str = "related",
              metadata: dict = None) -> bool:
    """
    Crea una asociacion dirigida:  pattern_id_a --[relation]--> pattern_id_b

    Args:
        pattern_id_a: ID del patron origen
        pattern_id_b: ID del patron destino
        relation:     Tipo de relacion (ver VALID_RELATIONS)
        metadata:     Datos adicionales de la relacion

    Returns:
        True si se creo, False si ya existia o inputs invalidos
    """
    if not pattern_id_a or not pattern_id_b or pattern_id_a == pattern_id_b:
        return False
    if relation not in VALID_RELATIONS:
        relation = "related"

    with file_lock("associative_graph"):
        graph = _load_graph()

        # Verificar si ya existe este edge exacto
        for edge in graph["edges"]:
            if (edge["from"]     == pattern_id_a and
                    edge["to"]   == pattern_id_b and
                    edge["relation"] == relation):
                return False  # ya existe

        # Registrar nodos si no existen
        now_iso = datetime.now(timezone.utc).isoformat()
        for pid in (pattern_id_a, pattern_id_b):
            if pid not in graph["nodes"]:
                graph["nodes"][pid] = {"id": pid, "added_at": now_iso}

        # Agregar edge
        graph["edges"].append({
            "from":       pattern_id_a,
            "to":         pattern_id_b,
            "relation":   relation,
            "created_at": now_iso,
            "metadata":   metadata or {},
        })

        _save_graph(graph)
    return True


def get_associations(pattern_id: str,
                     relation: str = None,
                     direction: str = "both") -> list:
    """
    Obtiene asociaciones de un patron.

    Args:
        pattern_id: ID del patron
        relation:   Filtrar por tipo (None = todos)
        direction:  "out" (salientes), "in" (entrantes), "both"

    Returns:
        Lista de {"pattern_id", "relation", "direction", "metadata"}
    """
    if not ASSOCIATIONS_FILE.exists():
        return []

    try:
        graph = _load_graph()
    except Exception:
        return []

    results = []
    for edge in graph["edges"]:
        if relation and edge["relation"] != relation:
            continue

        if direction in ("out", "both") and edge["from"] == pattern_id:
            results.append({
                "pattern_id": edge["to"],
                "relation":   edge["relation"],
                "direction":  "out",
                "metadata":   edge.get("metadata", {}),
            })

        if direction in ("in", "both") and edge["to"] == pattern_id:
            results.append({
                "pattern_id": edge["from"],
                "relation":   edge["relation"],
                "direction":  "in",
                "metadata":   edge.get("metadata", {}),
            })

    return results


def auto_associate_error_fix(error_pattern_id: str, fix_pattern_id: str):
    """
    Registra la relacion error->fix descubierta por learning_memory.
    Crea dos edges: fixes (fix->error) y caused_by (error->fix).
    """
    if not error_pattern_id or not fix_pattern_id:
        return
    associate(fix_pattern_id,   error_pattern_id, "fixes")
    associate(error_pattern_id, fix_pattern_id,   "caused_by")


def get_related_patterns(pattern_id: str, depth: int = 2) -> list:
    """
    Traversal BFS del grafo hasta profundidad N.

    Args:
        pattern_id: Patron de inicio
        depth:      Profundidad maxima de busqueda

    Returns:
        Lista de pattern_ids relacionados (sin el origen)
    """
    visited  = {pattern_id}
    frontier = {pattern_id}

    for _ in range(depth):
        next_frontier = set()
        for pid in frontier:
            for assoc in get_associations(pid):
                related = assoc["pattern_id"]
                if related not in visited:
                    next_frontier.add(related)
        visited.update(next_frontier)
        frontier = next_frontier

    return list(visited - {pattern_id})


def remove_association(pattern_id_a: str, pattern_id_b: str,
                       relation: str = None) -> int:
    """
    Elimina edges entre dos patrones.

    Args:
        relation: Si None, elimina todos los tipos entre ese par.

    Returns:
        Numero de edges eliminados
    """
    if not ASSOCIATIONS_FILE.exists():
        return 0

    with file_lock("associative_graph"):
        graph = _load_graph()
        before = len(graph["edges"])

        graph["edges"] = [
            e for e in graph["edges"]
            if not (
                e["from"] == pattern_id_a and
                e["to"]   == pattern_id_b and
                (relation is None or e["relation"] == relation)
            )
        ]

        removed = before - len(graph["edges"])
        if removed:
            _save_graph(graph)

    return removed


def get_stats() -> dict:
    """Estadisticas del grafo de asociaciones."""
    if not ASSOCIATIONS_FILE.exists():
        return {"nodes": 0, "edges": 0, "relation_types": {}}

    try:
        graph = _load_graph()
        rel_counts: dict = {}
        for edge in graph["edges"]:
            r = edge["relation"]
            rel_counts[r] = rel_counts.get(r, 0) + 1
        return {
            "nodes":          len(graph["nodes"]),
            "edges":          len(graph["edges"]),
            "relation_types": rel_counts,
        }
    except Exception:
        return {"nodes": 0, "edges": 0, "relation_types": {}}
