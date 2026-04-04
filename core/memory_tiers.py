#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
memory_tiers.py - Feature 12: Memoria Multinivel con Promocion/Degradacion
==========================================================================
Tres niveles de memoria tipo OS (inspirado en Letta/MemGPT):

  HOT  (RAM)     - Ultimo uso < 1h, acceso instantaneo, max 100 items
  WARM (Cache)   - Ultimo uso < 24h, acceso rapido, max 1000 items
  COLD (Archive) - Uso antiguo, acceso lento, sin limite

Promocion: un item en COLD que se consulta sube a WARM -> HOT
Degradacion: un item en HOT sin uso por >1h baja a WARM -> COLD
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger("memory_tiers")

TIERS_FILE = DATA_DIR / "memory_tiers.json"
TIER_METRICS_FILE = DATA_DIR / "memory_tier_metrics.json"

# Configuracion de niveles
TIER_CONFIG = {
    "hot": {
        "max_items": 100,
        "ttl_hours": 1,
        "description": "RAM - acceso instantaneo, datos activos",
    },
    "warm": {
        "max_items": 1000,
        "ttl_hours": 24,
        "description": "Cache - acceso rapido, datos recientes",
    },
    "cold": {
        "max_items": 0,  # sin limite
        "ttl_hours": 0,  # sin expiracion
        "description": "Archive - acceso lento, datos historicos",
    },
}


class MemoryTierManager:
    """Gestor de memoria multinivel."""

    def __init__(self):
        self._data = {"hot": [], "warm": [], "cold": []}
        self._loaded = False
        self._metrics = {
            "promotions": 0,
            "degradations": 0,
            "hot_hits": 0,
            "warm_hits": 0,
            "cold_hits": 0,
            "total_queries": 0,
        }

    def _load(self):
        if self._loaded:
            return
        if TIERS_FILE.exists():
            try:
                data = json.loads(TIERS_FILE.read_text(encoding="utf-8"))
                self._data = {
                    "hot": data.get("hot", []),
                    "warm": data.get("warm", []),
                    "cold": data.get("cold", []),
                }
            except Exception:
                pass
        if TIER_METRICS_FILE.exists():
            try:
                self._metrics = json.loads(TIER_METRICS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        self._loaded = True

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        save_data = {
            "hot": self._data["hot"],
            "warm": self._data["warm"],
            "cold": self._data["cold"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {t: len(items) for t, items in self._data.items()},
        }
        TIERS_FILE.write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        TIER_METRICS_FILE.write_text(
            json.dumps(self._metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def store(self, key: str, value: str, domain: str = "general",
              source: str = "unknown", tier: str = "hot") -> dict:
        """Almacena un item en el tier especificado."""
        self._load()

        item = {
            "key": key,
            "value": value[:2000],
            "domain": domain,
            "source": source,
            "tier": tier,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_access": datetime.now(timezone.utc).isoformat(),
            "access_count": 0,
            "promotion_count": 0,
        }

        # Verificar duplicados por key
        for t in ["hot", "warm", "cold"]:
            self._data[t] = [i for i in self._data[t] if i.get("key") != key]

        self._data[tier].append(item)
        self._enforce_limits()
        self._save()
        return item

    def query(self, key: str) -> dict | None:
        """Busca un item por key, promueve si lo encuentra en tier bajo."""
        self._load()
        self._metrics["total_queries"] = self._metrics.get("total_queries", 0) + 1

        for tier in ["hot", "warm", "cold"]:
            for item in self._data[tier]:
                if item.get("key") == key:
                    item["last_access"] = datetime.now(timezone.utc).isoformat()
                    item["access_count"] = item.get("access_count", 0) + 1
                    self._metrics[f"{tier}_hits"] = self._metrics.get(f"{tier}_hits", 0) + 1

                    # Promover si no esta en hot
                    if tier != "hot":
                        self._promote(item, tier)

                    self._save()
                    return item

        return None

    def search(self, query_text: str, top_n: int = 5) -> list[dict]:
        """Busca items por texto, priorizando tiers altos."""
        self._load()
        self._metrics["total_queries"] = self._metrics.get("total_queries", 0) + 1
        query_lower = query_text.lower()
        words = set(query_lower.split())

        scored = []
        for tier_idx, tier in enumerate(["hot", "warm", "cold"]):
            tier_bonus = (2 - tier_idx) * 0.1  # hot=+0.2, warm=+0.1, cold=+0.0
            for item in self._data[tier]:
                item_text = (item.get("key", "") + " " + item.get("value", "")).lower()
                item_words = set(item_text.split())

                # Score basado en overlap de palabras + bonus por tier
                overlap = len(words & item_words)
                if overlap == 0:
                    continue

                score = (overlap / max(len(words), 1)) + tier_bonus
                scored.append({
                    "item": item,
                    "tier": tier,
                    "score": round(score, 4),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Promover items encontrados en tiers bajos
        for s in scored[:top_n]:
            item = s["item"]
            tier = s["tier"]
            item["last_access"] = datetime.now(timezone.utc).isoformat()
            item["access_count"] = item.get("access_count", 0) + 1
            if tier != "hot":
                self._promote(item, tier)

        self._save()
        return scored[:top_n]

    def _promote(self, item: dict, current_tier: str):
        """Promueve un item a un tier superior."""
        promotion_map = {"cold": "warm", "warm": "hot"}
        target_tier = promotion_map.get(current_tier)
        if not target_tier:
            return

        # Remover del tier actual
        self._data[current_tier] = [
            i for i in self._data[current_tier] if i.get("key") != item.get("key")
        ]

        # Agregar al tier superior
        item["tier"] = target_tier
        item["promotion_count"] = item.get("promotion_count", 0) + 1
        self._data[target_tier].append(item)
        self._metrics["promotions"] = self._metrics.get("promotions", 0) + 1

        log.info(f"PROMOTED: '{item.get('key', '')[:50]}' {current_tier} -> {target_tier}")

    def run_degradation(self) -> int:
        """
        Degrada items que excedieron su TTL.
        Llamar periodicamente (ej: cada hora o al inicio de sesion).
        Returns: numero de items degradados.
        """
        self._load()
        now = datetime.now(timezone.utc)
        degraded = 0

        for tier in ["hot", "warm"]:
            ttl_hours = TIER_CONFIG[tier]["ttl_hours"]
            cutoff = now - timedelta(hours=ttl_hours)
            to_degrade = []
            remaining = []

            for item in self._data[tier]:
                last_access = item.get("last_access", item.get("created_at", ""))
                try:
                    access_dt = datetime.fromisoformat(last_access.replace("Z", "+00:00"))
                    if access_dt.tzinfo is None:
                        access_dt = access_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    access_dt = now  # No degradar si no se puede parsear

                if access_dt < cutoff:
                    to_degrade.append(item)
                else:
                    remaining.append(item)

            self._data[tier] = remaining

            # Degradar
            degrade_map = {"hot": "warm", "warm": "cold"}
            target = degrade_map[tier]
            for item in to_degrade:
                item["tier"] = target
                self._data[target].append(item)
                degraded += 1

        if degraded > 0:
            self._metrics["degradations"] = self._metrics.get("degradations", 0) + degraded
            self._save()
            log.info(f"DEGRADATION: {degraded} items moved down")

        return degraded

    def _enforce_limits(self):
        """Asegura que cada tier no exceda su maximo."""
        for tier, config in TIER_CONFIG.items():
            max_items = config["max_items"]
            if max_items > 0 and len(self._data[tier]) > max_items:
                # Mantener los mas recientes
                self._data[tier].sort(
                    key=lambda x: x.get("last_access", ""), reverse=True
                )
                overflow = self._data[tier][max_items:]
                self._data[tier] = self._data[tier][:max_items]

                # Mover overflow al tier inferior
                degrade_map = {"hot": "warm", "warm": "cold"}
                target = degrade_map.get(tier, "cold")
                for item in overflow:
                    item["tier"] = target
                    self._data[target].append(item)

    def get_stats(self) -> dict:
        """Estadisticas para dashboard."""
        self._load()
        return {
            "counts": {t: len(items) for t, items in self._data.items()},
            "total_items": sum(len(items) for items in self._data.values()),
            "metrics": self._metrics,
            "config": {t: {"max": c["max_items"], "ttl_h": c["ttl_hours"]}
                       for t, c in TIER_CONFIG.items()},
        }

    def import_from_kb(self, domain: str = "") -> int:
        """Importa entries existentes del KB como items COLD."""
        from config import KNOWLEDGE_DIR
        imported = 0
        files = [KNOWLEDGE_DIR / f"{domain}.json"] if domain else list(KNOWLEDGE_DIR.glob("*.json"))

        for kb_file in files[:30]:
            try:
                data = json.loads(kb_file.read_text(encoding="utf-8"))
                domain_name = kb_file.stem
                entries = []
                if isinstance(data, dict):
                    for section in data.values():
                        if isinstance(section, list):
                            entries.extend(section)
                elif isinstance(data, list):
                    entries.extend(data)

                for entry in entries[:200]:
                    key = entry.get("key", "")
                    value = entry.get("solution", entry.get("fact", ""))
                    if key and value:
                        self.store(key, value, domain=domain_name, source="kb_import", tier="cold")
                        imported += 1
            except Exception:
                continue

        return imported


# Singleton
_tier_manager = MemoryTierManager()


def store_memory(key: str, value: str, domain: str = "general",
                 source: str = "unknown", tier: str = "hot") -> dict:
    return _tier_manager.store(key, value, domain, source, tier)


def query_memory(key: str) -> dict | None:
    return _tier_manager.query(key)


def search_memory(query: str, top_n: int = 5) -> list[dict]:
    return _tier_manager.search(query, top_n)


def run_degradation() -> int:
    return _tier_manager.run_degradation()


def get_tier_stats() -> dict:
    return _tier_manager.get_stats()


def import_kb_to_tiers(domain: str = "") -> int:
    return _tier_manager.import_from_kb(domain)


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"

    if cmd == "stats":
        stats = get_tier_stats()
        print(f"Memory Tiers:")
        for tier, count in stats["counts"].items():
            cfg = TIER_CONFIG[tier]
            limit = cfg["max_items"] or "unlimited"
            print(f"  {tier.upper():6s}: {count} items (max: {limit}, TTL: {cfg['ttl_hours']}h)")
        print(f"Total: {stats['total_items']} items")
        m = stats["metrics"]
        print(f"Promotions: {m.get('promotions', 0)}, Degradations: {m.get('degradations', 0)}")

    elif cmd == "degrade":
        n = run_degradation()
        print(f"Degraded: {n} items")

    elif cmd == "import":
        domain = sys.argv[2] if len(sys.argv) > 2 else ""
        n = import_kb_to_tiers(domain)
        print(f"Imported: {n} items to COLD tier")

    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else "SAP error"
        results = search_memory(q, top_n=5)
        print(f"Search: '{q}' -> {len(results)} results")
        for r in results:
            item = r["item"]
            print(f"  [{r['tier'].upper()}] score={r['score']:.3f} | {item.get('key', '')[:60]}")

    else:
        print("Usage: memory_tiers.py [stats|degrade|import|search] [args]")
