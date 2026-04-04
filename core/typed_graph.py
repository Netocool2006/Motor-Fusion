#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
typed_graph.py - Feature 15: Graph con Relaciones Tipadas + Inferencia
=====================================================================
Extiende domain_graph.py con:
  - Relaciones tipadas: "X trabaja_con Y", "X depende_de Y", etc.
  - Inferencia automatica de tipos basada en contexto
  - Entidades (no solo dominios): archivos, comandos, errores, personas
  - Queries tipo: "que archivos se relacionan con SAP?"

Inspirado en: Mem0 Graph Memory + mcp-memory-service Knowledge Graph
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from config import DATA_DIR, KNOWLEDGE_DIR

log = logging.getLogger("typed_graph")

TYPED_GRAPH_FILE = DATA_DIR / "typed_graph.json"
TYPED_GRAPH_METRICS = DATA_DIR / "typed_graph_metrics.json"

# Tipos de relaciones soportadas
RELATION_TYPES = {
    "depends_on": "A depende de B",
    "part_of": "A es parte de B",
    "used_with": "A se usa junto con B",
    "solves": "A resuelve B",
    "causes": "A causa B",
    "related_to": "A se relaciona con B (generico)",
    "alternative_to": "A es alternativa a B",
    "configures": "A configura B",
    "imports": "A importa B",
    "triggers": "A dispara/trigger B",
}

# Tipos de entidades
ENTITY_TYPES = {
    "domain": "Dominio del KB",
    "file": "Archivo de codigo",
    "command": "Comando de terminal",
    "error": "Error o excepcion",
    "concept": "Concepto o tecnologia",
    "person": "Persona o usuario",
    "service": "Servicio externo",
}


class TypedGraph:
    """Grafo con relaciones tipadas y entidades."""

    def __init__(self):
        self._entities = {}  # id -> {type, name, properties}
        self._relations = []  # [{source, target, type, weight, context}]
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if TYPED_GRAPH_FILE.exists():
            try:
                data = json.loads(TYPED_GRAPH_FILE.read_text(encoding="utf-8"))
                self._entities = data.get("entities", {})
                self._relations = data.get("relations", [])
            except Exception:
                pass
        self._loaded = True

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "entities": self._entities,
            "relations": self._relations,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "entities": len(self._entities),
                "relations": len(self._relations),
            },
        }
        TYPED_GRAPH_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add_entity(self, entity_id: str, entity_type: str, name: str = "",
                   properties: dict = None) -> dict:
        """Agrega o actualiza una entidad."""
        self._load()
        entity = self._entities.get(entity_id, {})
        entity.update({
            "id": entity_id,
            "type": entity_type,
            "name": name or entity_id,
            "properties": properties or entity.get("properties", {}),
            "created_at": entity.get("created_at", datetime.now(timezone.utc).isoformat()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        self._entities[entity_id] = entity
        self._save()
        return entity

    def add_relation(self, source: str, target: str, relation_type: str,
                     weight: float = 1.0, context: str = "") -> dict:
        """Agrega una relacion tipada entre dos entidades."""
        self._load()

        # Auto-crear entidades si no existen
        if source not in self._entities:
            self.add_entity(source, _infer_entity_type(source), source)
        if target not in self._entities:
            self.add_entity(target, _infer_entity_type(target), target)

        # Verificar si la relacion ya existe
        for rel in self._relations:
            if (rel["source"] == source and rel["target"] == target
                    and rel["type"] == relation_type):
                rel["weight"] = rel.get("weight", 1.0) + weight
                rel["updated_at"] = datetime.now(timezone.utc).isoformat()
                if context:
                    rel["context"] = context
                self._save()
                return rel

        # Nueva relacion
        rel = {
            "source": source,
            "target": target,
            "type": relation_type,
            "weight": weight,
            "context": context,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._relations.append(rel)
        self._save()
        return rel

    def query_entity(self, entity_id: str) -> dict:
        """Obtiene una entidad con todas sus relaciones."""
        self._load()
        entity = self._entities.get(entity_id)
        if not entity:
            return {"found": False}

        outgoing = [r for r in self._relations if r["source"] == entity_id]
        incoming = [r for r in self._relations if r["target"] == entity_id]

        return {
            "found": True,
            "entity": entity,
            "outgoing": outgoing,
            "incoming": incoming,
            "total_relations": len(outgoing) + len(incoming),
        }

    def query_by_type(self, relation_type: str, top_n: int = 20) -> list[dict]:
        """Busca todas las relaciones de un tipo."""
        self._load()
        matches = [r for r in self._relations if r["type"] == relation_type]
        matches.sort(key=lambda x: x.get("weight", 0), reverse=True)
        return matches[:top_n]

    def find_paths(self, source: str, target: str, max_depth: int = 3) -> list[list[dict]]:
        """Encuentra caminos entre dos entidades."""
        self._load()
        paths = []
        visited = set()

        def _dfs(current, path, depth):
            if depth > max_depth:
                return
            if current == target:
                paths.append(list(path))
                return
            if current in visited:
                return
            visited.add(current)

            for rel in self._relations:
                if rel["source"] == current:
                    path.append(rel)
                    _dfs(rel["target"], path, depth + 1)
                    path.pop()

            visited.discard(current)

        _dfs(source, [], 0)
        return paths[:10]

    def infer_relations(self, text: str) -> list[dict]:
        """
        Inferencia automatica: extrae entidades y relaciones de texto libre.
        Precision objetivo: ~80% (similar a mcp-memory-service 93.5%)
        """
        self._load()
        inferred = []

        # Patron 1: "X depende de Y"
        dep_patterns = [
            (r"(\w+(?:\.\w+)?)\s+(?:depende de|depends on|requires|necesita)\s+(\w+(?:\.\w+)?)",
             "depends_on"),
            (r"(\w+(?:\.\w+)?)\s+(?:usa|uses|utiliza)\s+(\w+(?:\.\w+)?)",
             "used_with"),
            (r"(\w+(?:\.\w+)?)\s+(?:importa|imports)\s+(\w+(?:\.\w+)?)",
             "imports"),
            (r"(\w+(?:\.\w+)?)\s+(?:resuelve|solves|fixes|arregla)\s+(.+?)(?:\.|$)",
             "solves"),
            (r"(\w+(?:\.\w+)?)\s+(?:causa|causes|provoca|triggers)\s+(.+?)(?:\.|$)",
             "causes"),
            (r"(\w+(?:\.\w+)?)\s+(?:es parte de|is part of|pertenece a)\s+(\w+(?:\.\w+)?)",
             "part_of"),
            (r"(\w+(?:\.\w+)?)\s+(?:configura|configures|setea|sets up)\s+(\w+(?:\.\w+)?)",
             "configures"),
            (r"(\w+(?:\.\w+)?)\s+(?:dispara|triggers|activa|activates)\s+(\w+(?:\.\w+)?)",
             "triggers"),
        ]

        for pattern, rel_type in dep_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for source, target in matches:
                source = source.strip().lower()
                target = target.strip().lower()[:50]
                if len(source) > 2 and len(target) > 2:
                    inferred.append({
                        "source": source,
                        "target": target,
                        "type": rel_type,
                        "confidence": 0.7,
                    })

        # Patron 2: Archivos mencionados juntos = used_with
        file_refs = re.findall(r'[\w/\\]+\.\w{2,4}', text)
        if len(file_refs) >= 2:
            for i in range(len(file_refs)):
                for j in range(i + 1, min(i + 3, len(file_refs))):
                    inferred.append({
                        "source": file_refs[i],
                        "target": file_refs[j],
                        "type": "used_with",
                        "confidence": 0.5,
                    })

        # Patron 3: Error -> archivo = related_to
        error_match = re.search(r'(?:error|exception|traceback)\s+(?:in|en)\s+([\w/\\]+\.\w{2,4})', text, re.IGNORECASE)
        if error_match:
            inferred.append({
                "source": "error:" + text[:50].replace(" ", "_"),
                "target": error_match.group(1),
                "type": "related_to",
                "confidence": 0.8,
            })

        return inferred

    def auto_infer_and_store(self, text: str, context: str = "") -> int:
        """Infiere relaciones de texto y las almacena automaticamente."""
        inferred = self.infer_relations(text)
        stored = 0
        for rel in inferred:
            if rel["confidence"] >= 0.5:
                self.add_relation(
                    source=rel["source"],
                    target=rel["target"],
                    relation_type=rel["type"],
                    weight=rel["confidence"],
                    context=context[:200],
                )
                stored += 1
        return stored

    def import_from_domain_graph(self) -> int:
        """Importa el grafo simple existente como relaciones tipadas."""
        imported = 0
        try:
            from core.domain_graph import build_graph
            G = build_graph()
            for u, v, data in G.edges(data=True):
                weight = data.get("weight", 1)
                sources = data.get("sources", set())

                # Determinar tipo de relacion
                if "static" in sources:
                    rel_type = "related_to"
                elif "cooccurrence" in sources:
                    rel_type = "used_with"
                elif "markov" in sources:
                    rel_type = "triggers"
                else:
                    rel_type = "related_to"

                self.add_entity(u, "domain", u)
                self.add_entity(v, "domain", v)
                self.add_relation(u, v, rel_type, weight=weight)
                imported += 1
        except Exception as e:
            log.error(f"Import error: {e}")
        return imported

    def get_stats(self) -> dict:
        self._load()
        entity_types = defaultdict(int)
        for e in self._entities.values():
            entity_types[e.get("type", "unknown")] += 1

        relation_types = defaultdict(int)
        for r in self._relations:
            relation_types[r.get("type", "unknown")] += 1

        return {
            "entities": len(self._entities),
            "relations": len(self._relations),
            "entity_types": dict(entity_types),
            "relation_types": dict(relation_types),
        }


# Singleton
_typed_graph = TypedGraph()


def _infer_entity_type(entity_id: str) -> str:
    """Infiere el tipo de entidad por su nombre."""
    if re.match(r'.*\.\w{2,4}$', entity_id):
        return "file"
    if re.match(r'^(pip|npm|git|python|docker|cd|ls|cat)\b', entity_id):
        return "command"
    if re.match(r'(?i)^(error|exception|traceback)', entity_id):
        return "error"
    if entity_id.islower() and "_" in entity_id:
        return "domain"
    return "concept"


def add_entity(entity_id: str, entity_type: str, name: str = "",
               properties: dict = None) -> dict:
    return _typed_graph.add_entity(entity_id, entity_type, name, properties)


def add_relation(source: str, target: str, relation_type: str,
                 weight: float = 1.0, context: str = "") -> dict:
    return _typed_graph.add_relation(source, target, relation_type, weight, context)


def query_entity(entity_id: str) -> dict:
    return _typed_graph.query_entity(entity_id)


def query_by_type(relation_type: str, top_n: int = 20) -> list[dict]:
    return _typed_graph.query_by_type(relation_type, top_n)


def find_paths(source: str, target: str) -> list[list[dict]]:
    return _typed_graph.find_paths(source, target)


def infer_and_store(text: str, context: str = "") -> int:
    return _typed_graph.auto_infer_and_store(text, context)


def import_from_domain_graph() -> int:
    return _typed_graph.import_from_domain_graph()


def get_typed_graph_stats() -> dict:
    return _typed_graph.get_stats()


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"

    if cmd == "stats":
        stats = get_typed_graph_stats()
        print(f"Typed Graph:")
        print(f"  Entities: {stats['entities']}")
        print(f"  Relations: {stats['relations']}")
        if stats['entity_types']:
            print(f"  Entity types: {stats['entity_types']}")
        if stats['relation_types']:
            print(f"  Relation types: {stats['relation_types']}")

    elif cmd == "import":
        print("Importing from domain_graph...")
        n = import_from_domain_graph()
        print(f"Imported: {n} relations")
        stats = get_typed_graph_stats()
        print(f"Now: {stats['entities']} entities, {stats['relations']} relations")

    elif cmd == "infer":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "config.py importa knowledge_base.py y depende de vector_kb"
        print(f"Inferring from: '{text}'")
        n = infer_and_store(text)
        print(f"Stored: {n} relations")

    elif cmd == "query":
        entity = sys.argv[2] if len(sys.argv) > 2 else "sap_tierra"
        result = query_entity(entity)
        if result["found"]:
            print(f"Entity: {result['entity']['name']} ({result['entity']['type']})")
            print(f"Outgoing: {len(result['outgoing'])}")
            for r in result['outgoing'][:10]:
                print(f"  -> {r['type']} -> {r['target']} (w={r.get('weight', 0):.1f})")
            print(f"Incoming: {len(result['incoming'])}")
            for r in result['incoming'][:10]:
                print(f"  <- {r['type']} <- {r['source']} (w={r.get('weight', 0):.1f})")
        else:
            print(f"Entity '{entity}' not found")

    elif cmd == "types":
        print("Relation types:")
        for t, desc in RELATION_TYPES.items():
            print(f"  {t:20s} - {desc}")
        print("\nEntity types:")
        for t, desc in ENTITY_TYPES.items():
            print(f"  {t:12s} - {desc}")

    else:
        print("Usage: typed_graph.py [stats|import|infer|query|types] [args]")
