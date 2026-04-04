#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
async_memory.py - Feature 10: Async Memory / Non-Blocking Save
===============================================================
Cola async para guardar aprendizaje sin bloquear la sesión.
El hook retorna inmediato, un worker procesa la cola en background.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty

from config import DATA_DIR

log = logging.getLogger("async_memory")

QUEUE_FILE = DATA_DIR / "async_memory_queue.json"
METRICS_FILE = DATA_DIR / "async_memory_metrics.json"
MAX_QUEUE_SIZE = 200
BATCH_SIZE = 10
WORKER_INTERVAL = 5  # seconds


class MemoryQueue:
    """Cola persistente de operaciones de memoria."""

    def __init__(self):
        self._queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self._worker_thread = None
        self._running = False
        self._metrics = {
            "enqueued": 0,
            "processed": 0,
            "errors": 0,
            "avg_process_ms": 0,
        }

    def enqueue(self, operation: dict) -> bool:
        """Agrega una operación a la cola (non-blocking)."""
        operation["enqueued_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._queue.put_nowait(operation)
            self._metrics["enqueued"] += 1
            self._persist_queue()
            return True
        except Exception:
            # Cola llena, guardar en disco
            self._persist_to_disk(operation)
            return True

    def _persist_to_disk(self, operation: dict):
        """Fallback: guarda en disco si la cola en memoria está llena."""
        queue_data = self._load_disk_queue()
        queue_data.append(operation)
        if len(queue_data) > MAX_QUEUE_SIZE:
            queue_data = queue_data[-MAX_QUEUE_SIZE:]
        self._save_disk_queue(queue_data)

    def _load_disk_queue(self) -> list:
        if QUEUE_FILE.exists():
            try:
                return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_disk_queue(self, data: list):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        QUEUE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _persist_queue(self):
        """Persiste la cola en memoria a disco."""
        items = []
        temp_queue = Queue()
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                items.append(item)
                temp_queue.put(item)
            except Empty:
                break
        # Restaurar cola
        while not temp_queue.empty():
            try:
                self._queue.put_nowait(temp_queue.get_nowait())
            except Exception:
                break
        if items:
            existing = self._load_disk_queue()
            existing.extend(items)
            if len(existing) > MAX_QUEUE_SIZE:
                existing = existing[-MAX_QUEUE_SIZE:]
            self._save_disk_queue(existing)

    def process_batch(self) -> int:
        """Procesa un batch de operaciones. Retorna cantidad procesada."""
        processed = 0
        batch = []

        # Primero de memoria
        for _ in range(BATCH_SIZE):
            try:
                item = self._queue.get_nowait()
                batch.append(item)
            except Empty:
                break

        # Si no hay suficientes, del disco
        if len(batch) < BATCH_SIZE:
            disk_queue = self._load_disk_queue()
            remaining = BATCH_SIZE - len(batch)
            batch.extend(disk_queue[:remaining])
            self._save_disk_queue(disk_queue[remaining:])

        for op in batch:
            start = time.time()
            try:
                self._process_operation(op)
                elapsed_ms = (time.time() - start) * 1000
                self._metrics["processed"] += 1
                # Running average
                prev_avg = self._metrics["avg_process_ms"]
                n = self._metrics["processed"]
                self._metrics["avg_process_ms"] = round(prev_avg + (elapsed_ms - prev_avg) / n, 1)
                processed += 1
            except Exception as e:
                self._metrics["errors"] += 1
                log.error(f"Async process error: {e}")

        self._save_metrics()
        return processed

    def _process_operation(self, op: dict):
        """Ejecuta una operación de memoria."""
        op_type = op.get("type", "")

        if op_type == "add_pattern":
            from core.knowledge_base import add_pattern
            add_pattern(
                domain=op.get("domain", "general"),
                key=op.get("key", ""),
                solution=op.get("solution", ""),
                tags=op.get("tags", []),
            )
        elif op_type == "add_fact":
            from core.knowledge_base import add_fact
            add_fact(
                domain=op.get("domain", "general"),
                key=op.get("key", ""),
                fact=op.get("fact", ""),
                tags=op.get("tags", []),
            )
        elif op_type == "record_convention":
            from core.passive_capture import record_convention
            record_convention(
                pattern=op.get("pattern", ""),
                context=op.get("context", ""),
            )
        elif op_type == "learn_route":
            from core.smart_file_routing import learn_route
            learn_route(
                task_keywords=op.get("keywords", []),
                files_touched=op.get("files", []),
            )
        elif op_type == "strengthen_edge":
            from core.domain_graph import strengthen_edge
            strengthen_edge(
                domain_a=op.get("domain_a", ""),
                domain_b=op.get("domain_b", ""),
            )
        elif op_type == "cloud_sync_enqueue":
            from core.cloud_sync import enqueue_change
            enqueue_change(
                domain=op.get("domain", ""),
                change_type=op.get("change_type", ""),
                key=op.get("key", ""),
            )
        else:
            log.warning(f"Unknown async operation type: {op_type}")

    def _save_metrics(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        METRICS_FILE.write_text(json.dumps(self._metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_metrics(self) -> dict:
        if METRICS_FILE.exists():
            try:
                return json.loads(METRICS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._metrics

    def get_queue_size(self) -> int:
        return self._queue.qsize() + len(self._load_disk_queue())


# Singleton
_memory_queue = MemoryQueue()


def enqueue_async(operation: dict) -> bool:
    """API pública: encola una operación de memoria."""
    return _memory_queue.enqueue(operation)


def process_pending() -> int:
    """API pública: procesa operaciones pendientes (llamar desde post-hook)."""
    return _memory_queue.process_batch()


def get_async_stats() -> dict:
    """Estadísticas para dashboard."""
    metrics = _memory_queue.get_metrics()
    metrics["queue_size"] = _memory_queue.get_queue_size()
    return metrics


# CLI
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "process":
        n = process_pending()
        print(f"Procesadas: {n} operaciones")
    elif cmd == "stats":
        stats = get_async_stats()
        print(f"Queue: {stats.get('queue_size', 0)} pending")
        print(f"Processed: {stats.get('processed', 0)}")
        print(f"Errors: {stats.get('errors', 0)}")
        print(f"Avg time: {stats.get('avg_process_ms', 0)}ms")
    else:
        print("Usage: async_memory.py [process|stats]")
