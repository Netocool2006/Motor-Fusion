#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Motor_IA Dashboard v2 - Monitoreo del sistema RAG completo"""
import sys
import json
import os
import subprocess
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from datetime import datetime

_PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT))
HTML_FILE = Path(__file__).parent / "index.html"

# -- Ingest Logger (dedicated file) ----------------------------------------
import logging
_INGEST_LOG_FILE = _PROJECT / "core" / "ingest.log"
_ingest_logger = logging.getLogger("mass_ingest")
_ingest_logger.setLevel(logging.INFO)
_ingest_fh = logging.FileHandler(str(_INGEST_LOG_FILE), encoding="utf-8")
_ingest_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_ingest_logger.addHandler(_ingest_fh)

# -- Mass Ingest State (shared between thread and handler) --------------------
_ingest_state = {
    "running": False,
    "progress": 0,
    "message": "Idle",
    "phase": "",
    "domains_found": 0,
    "files_processed": 0,
    "facts_ingested": 0,
    "duplicates_skipped": 0,
    "errors": [],
    "results": {},
    "started_at": None,
    "finished_at": None,
}
_ingest_lock = threading.Lock()


def _update_ingest_state(**kwargs):
    with _ingest_lock:
        _ingest_state.update(kwargs)


def _get_ingest_state():
    with _ingest_lock:
        return dict(_ingest_state)


def _run_mass_ingest(scan_path, depth=3, min_files=3, max_files_per_domain=50):
    """Runs mass ingest in a background thread with deduplication."""
    try:
        ilog = _ingest_logger
        ilog.info("=" * 60)
        ilog.info(f"INGEST START: path={scan_path} depth={depth} min_files={min_files} max_per_domain={max_files_per_domain}")

        _update_ingest_state(
            running=True, progress=0, message="Iniciando escaneo...",
            phase="scan", domains_found=0, files_processed=0,
            facts_ingested=0, duplicates_skipped=0, errors=[],
            results={}, started_at=datetime.now().isoformat(),
            finished_at=None,
        )

        from core.disk_scanner import scan, _cluster_by_folder, \
            _extract_file_keywords, _suggest_domain_name, _calculate_confidence, \
            STOP_WORDS as SCAN_STOP_WORDS
        from core.domain_detector import learn_domain_keywords
        from core.file_extractor import extract_text, can_extract, chunk_text
        from core.knowledge_base import add_fact

        # Dedup via ChromaDB similarity check
        dedup_collection = None
        dedup_embedder = None
        try:
            from core.vector_kb import _get_collection, _get_embedder
            dedup_collection = _get_collection()
            dedup_embedder = _get_embedder()
            ilog.info("ChromaDB dedup: ENABLED")
        except Exception as e:
            ilog.warning(f"ChromaDB dedup: DISABLED ({e})")

        scan_paths = [scan_path]

        # Phase 1: Scan
        _update_ingest_state(progress=5, message=f"Escaneando {scan_path}...", phase="scan")
        ilog.info(f"PHASE 1: Scanning {scan_path}...")

        results = scan(scan_paths, depth=depth, min_files=min_files)
        if not results:
            ilog.warning("SCAN: No domains found. Aborting.")
            _update_ingest_state(
                running=False, progress=100,
                message="No se encontraron dominios en la ruta indicada.",
                phase="done", finished_at=datetime.now().isoformat(),
            )
            return

        ilog.info(f"SCAN: {len(results)} domains discovered: {', '.join(results.keys())}")

        _update_ingest_state(
            progress=15, domains_found=len(results),
            message=f"{len(results)} dominios descubiertos. Creando dominios...",
            phase="create_domains",
        )

        # Phase 2: Create domains
        ilog.info(f"PHASE 2: Creating domains (confidence >= 0.4)...")
        valid_domains = {}
        for domain_name, info in results.items():
            if info["confidence"] >= 0.4 and info["keywords"]:
                try:
                    learn_domain_keywords(domain_name, info["keywords"])
                    info["saved"] = True
                    valid_domains[domain_name] = info
                    ilog.info(f"  DOMAIN CREATED: {domain_name} (conf={info['confidence']:.2f}, keywords={info['keywords'][:5]})")
                except Exception as e:
                    info["saved"] = False
                    _ingest_state["errors"].append(f"Domain {domain_name}: {e}")
                    ilog.error(f"  DOMAIN FAILED: {domain_name}: {e}")
            else:
                ilog.info(f"  DOMAIN SKIPPED: {domain_name} (conf={info.get('confidence',0):.2f}, too low)")

        ilog.info(f"DOMAINS: {len(valid_domains)} created, {len(results) - len(valid_domains)} skipped")

        _update_ingest_state(
            progress=20,
            message=f"{len(valid_domains)} dominios creados. Ingiriendo archivos...",
            phase="ingest",
        )

        # Phase 3: Ingest files with dedup
        ilog.info(f"PHASE 3: Ingesting files with dedup...")
        # Re-scan to get file lists (scan() doesn't return files, need clusters)
        clusters = _cluster_by_folder(scan_paths, depth)

        total_files = 0
        total_facts = 0
        total_dupes = 0
        domain_idx = 0
        total_domains = max(len(valid_domains), 1)

        for domain_name, info in valid_domains.items():
            domain_idx += 1
            pct = 20 + int((domain_idx / total_domains) * 75)
            _update_ingest_state(
                progress=pct,
                message=f"[{domain_idx}/{total_domains}] Ingiriendo: {domain_name}",
            )

            # Find matching cluster
            cluster_files = []
            for folder_name, cluster in clusters.items():
                suggested = _suggest_domain_name(folder_name, cluster["keywords"])
                if suggested == domain_name:
                    cluster_files = cluster["files"]
                    break

            if not cluster_files:
                ilog.info(f"  [{domain_idx}/{total_domains}] {domain_name}: no matching cluster found, skipping")
                continue

            # Filter extractable files
            extractable = [f for f in cluster_files if can_extract(f)]
            extractable.sort(
                key=lambda f: f.stat().st_size if f.exists() else 0,
                reverse=True,
            )
            extractable = extractable[:max_files_per_domain]

            domain_facts = 0
            domain_dupes = 0
            ilog.info(f"  [{domain_idx}/{total_domains}] {domain_name}: {len(extractable)} files to process")

            for fpath in extractable:
                try:
                    text = extract_text(fpath, max_chars=5000)
                    if not text or len(text.strip()) < 50:
                        continue

                    chunks = chunk_text(text, chunk_size=800, overlap=100)
                    total_files += 1

                    for c_idx, chunk in enumerate(chunks):
                        if not chunk.strip() or len(chunk.strip()) < 30:
                            continue

                        # -- DEDUP CHECK via ChromaDB similarity --
                        is_duplicate = False
                        emb = None
                        if dedup_collection and dedup_embedder:
                            try:
                                emb = dedup_embedder.encode(
                                    [chunk[:500]], show_progress_bar=False
                                ).tolist()
                                hits = dedup_collection.query(
                                    query_embeddings=emb, n_results=1,
                                )
                                if (hits["distances"] and hits["distances"][0]
                                        and hits["distances"][0][0] < 0.08):
                                    # cosine distance < 0.08 means similarity > 0.92
                                    is_duplicate = True
                                    domain_dupes += 1
                            except Exception:
                                pass

                        if is_duplicate:
                            ilog.info(f"    DUPLICATE: {fpath.name} chunk#{c_idx} (similarity > 92%)")
                            continue

                        # Save to KB
                        fact_key = f"{fpath.stem}_{c_idx}"
                        tags = []
                        ext = fpath.suffix.lower()
                        from core.disk_scanner import EXT_CATEGORIES
                        if ext in EXT_CATEGORIES:
                            tags.append(EXT_CATEGORIES[ext])
                        tags.append(ext.lstrip('.'))

                        fact = {
                            "rule": chunk,
                            "applies_to": domain_name,
                            "source": str(fpath),
                            "confidence": "observed",
                            "examples": [],
                            "exceptions": "",
                        }

                        try:
                            add_fact(domain_name, fact_key, fact, tags=tags)
                            domain_facts += 1

                            # Index directly into ChromaDB for real-time dedup
                            if dedup_collection and dedup_embedder:
                                try:
                                    doc_id = f"ingest_{domain_name}_{fact_key}"
                                    if not emb:
                                        emb = dedup_embedder.encode(
                                            [chunk[:500]], show_progress_bar=False
                                        ).tolist()
                                    dedup_collection.add(
                                        ids=[doc_id],
                                        embeddings=emb,
                                        documents=[chunk[:500]],
                                        metadatas=[{
                                            "domain": domain_name,
                                            "type": "fact",
                                            "key": fact_key,
                                            "source": "mass_ingest",
                                        }],
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            pass

                except Exception:
                    continue

            total_facts += domain_facts
            total_dupes += domain_dupes

            info["files_ingested"] = total_files
            info["facts_ingested"] = domain_facts
            info["duplicates_skipped"] = domain_dupes

            ilog.info(f"  DOMAIN DONE: {domain_name} -> {domain_facts} facts saved, {domain_dupes} duplicates skipped")

            _update_ingest_state(
                files_processed=total_files,
                facts_ingested=total_facts,
                duplicates_skipped=total_dupes,
            )

        # Phase 4: Index new content into ChromaDB
        ilog.info(f"PHASE 4: Indexing into ChromaDB...")
        _update_ingest_state(
            progress=96,
            message="Indexando en ChromaDB...",
            phase="index",
        )
        try:
            from core.vector_kb import index_knowledge_base
            idx_result = index_knowledge_base()
            indexed = idx_result.get("indexed", 0)
            ilog.info(f"INDEX: {indexed} documents indexed in ChromaDB")
        except Exception as e:
            indexed = 0
            ilog.error(f"INDEX ERROR: {e}")

        final_msg = (
            f"Completo: {len(valid_domains)} dominios, "
            f"{total_files} archivos, {total_facts} facts, "
            f"{total_dupes} duplicados omitidos, "
            f"{indexed} indexados en ChromaDB"
        )
        ilog.info(f"INGEST COMPLETE: {final_msg}")
        ilog.info("=" * 60)

        _update_ingest_state(
            running=False, progress=100,
            message=final_msg,
            phase="done", results=_serialize_results(results),
            finished_at=datetime.now().isoformat(),
        )

    except Exception as e:
        ilog.error(f"FATAL ERROR: {e}")
        _update_ingest_state(
            running=False, progress=100,
            message=f"Error fatal: {e}",
            phase="error",
            finished_at=datetime.now().isoformat(),
        )


def _serialize_results(results):
    """Convert results to JSON-safe dict."""
    safe = {}
    for name, info in results.items():
        safe[name] = {
            "keywords": info.get("keywords", [])[:10],
            "files_found": info.get("files_found", 0),
            "confidence": info.get("confidence", 0),
            "saved": info.get("saved", False),
            "facts_ingested": info.get("facts_ingested", 0),
            "duplicates_skipped": info.get("duplicates_skipped", 0),
        }
    return safe


def _read_log_tail(filepath, n=30):
    """Lee las últimas n líneas de un log."""
    try:
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-n:]
        return [l.strip() for l in lines if l.strip()]
    except Exception:
        return []


def _check_chromadb():
    """Verifica estado de ChromaDB."""
    try:
        from core.vector_kb import get_stats
        stats = get_stats()
        return {
            "status": "OK" if stats.get("total", 0) > 0 else "EMPTY",
            "total_docs": stats.get("total", 0),
            "facts": stats.get("facts", 0),
            "patterns": stats.get("patterns", 0),
            "learned": stats.get("learned", 0),
            "sessions": stats.get("sessions", 0),
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "total_docs": 0}


def _check_kb_cache():
    """Verifica estado del cache TF-IDF."""
    cache_file = _PROJECT / "core" / "kb_cache.json"
    try:
        if not cache_file.exists():
            return {"status": "EMPTY", "entries": 0}
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        active = [e for e in data if (time.time() - e.get("timestamp", 0)) / 3600 < 168]
        return {"status": "OK", "entries": len(data), "active": len(active)}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def _check_knowledge_local():
    """Verifica knowledge/ local (backup)."""
    kb_path = _PROJECT / "knowledge"
    if not kb_path.exists():
        return {"status": "MISSING", "domains": 0, "size_mb": 0}
    domains = [d for d in kb_path.iterdir() if d.is_dir()]
    total_size = sum(f.stat().st_size for d in domains for f in d.rglob("*") if f.is_file())
    return {
        "status": "OK",
        "domains": len(domains),
        "size_mb": round(total_size / 1024 / 1024, 1),
        "domain_list": sorted(d.name for d in domains),
    }


def _check_hooks():
    """Verifica que los hooks estén registrados en settings.json."""
    # Find settings.json
    settings_paths = [
        Path.home() / "AppData" / "Local" / "ClaudeCode" / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
    ]
    for sp in settings_paths:
        if sp.exists():
            try:
                with open(sp, encoding="utf-8") as f:
                    settings = json.load(f)
                hooks = settings.get("hooks", {})
                pre = hooks.get("UserPromptSubmit", [])
                post = hooks.get("Stop", [])
                pre_ok = any("motor_ia_hook" in str(h) for h in pre) if pre else False
                post_ok = any("motor_ia_post_hook" in str(h) for h in post) if post else False
                return {
                    "status": "OK" if pre_ok and post_ok else "PARTIAL",
                    "pre_hook": "REGISTERED" if pre_ok else "MISSING",
                    "post_hook": "REGISTERED" if post_ok else "MISSING",
                    "settings_path": str(sp),
                }
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}
    return {"status": "NOT_FOUND", "pre_hook": "UNKNOWN", "post_hook": "UNKNOWN"}


def _parse_motor_ia_log():
    """Parsea el log principal para métricas."""
    log_file = _PROJECT / "core" / "motor_ia_hook.log"
    lines = _read_log_tail(log_file, 100)

    queries_today = 0
    cache_hits = 0
    vector_hits = 0
    internet_searches = 0
    auto_saves = 0
    errors = 0
    last_query = ""
    last_result = ""
    today = datetime.now().strftime("%Y-%m-%d")

    recent_activity = []

    for line in lines:
        if today not in line:
            continue
        if "QUERY:" in line:
            queries_today += 1
            last_query = line.split("QUERY:")[1].strip()[:80]
        if "CACHE HIT" in line:
            cache_hits += 1
        if "source=vector_kb" in line:
            vector_hits += 1
        if "FORCING web search" in line or "Web search:" in line:
            internet_searches += 1
        if "AUTO-SAVED" in line:
            auto_saves += 1
        if "[ERROR]" in line:
            errors += 1
        if "RESULT:" in line:
            last_result = line.split("RESULT:")[1].strip()[:100]
            # Extract for recent activity
            ts = line[:19] if len(line) > 19 else ""
            recent_activity.append({"time": ts, "result": last_result})

    return {
        "queries_today": queries_today,
        "cache_hits": cache_hits,
        "vector_hits": vector_hits,
        "internet_searches": internet_searches,
        "auto_saves": auto_saves,
        "errors": errors,
        "last_query": last_query,
        "last_result": last_result,
        "recent_activity": recent_activity[-10:],
    }


def _check_state():
    """Lee el estado actual del motor."""
    state_file = _PROJECT / "core" / "motor_ia_state.json"
    try:
        if not state_file.exists():
            return {"status": "NO_STATE", "query": "", "kb_pct": 0}
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"status": "ERROR"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/ingest/start":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                params = json.loads(body) if body else {}
            except Exception:
                params = {}

            scan_path = params.get("path", "").strip()
            if not scan_path:
                self._send_json({"error": "Se requiere un path"}, 400)
                return

            # Validate path exists
            if not Path(scan_path).exists():
                self._send_json({"error": f"Path no existe: {scan_path}"}, 400)
                return

            # Check if already running
            state = _get_ingest_state()
            if state["running"]:
                self._send_json({"error": "Ya hay una ingestion en curso"}, 409)
                return

            depth = int(params.get("depth", 3))
            min_files = int(params.get("min_files", 3))
            max_files = int(params.get("max_files_per_domain", 50))

            # Launch in background thread
            t = threading.Thread(
                target=_run_mass_ingest,
                args=(scan_path, depth, min_files, max_files),
                daemon=True,
            )
            t.start()

            self._send_json({"status": "started", "path": scan_path})
            return

        elif self.path == "/api/ingest/stop":
            _update_ingest_state(
                running=False, message="Detenido por el usuario",
                phase="stopped", finished_at=datetime.now().isoformat(),
            )
            self._send_json({"status": "stopped"})
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            try:
                html = HTML_FILE.read_text(encoding="utf-8")
            except Exception:
                html = "<h1>Dashboard HTML not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/api/browse-folder":
            # Open native Windows folder picker via VBScript (gets foreground focus)
            try:
                import tempfile
                tmp = Path(tempfile.mktemp(suffix=".txt"))
                vbs = Path(__file__).parent / "browse_folder.vbs"
                # wscript runs as interactive process -> gets foreground focus
                result = subprocess.run(
                    ["wscript", str(vbs), str(tmp)],
                    timeout=120,
                )
                folder = ""
                if tmp.exists():
                    folder = tmp.read_text(encoding="utf-8", errors="ignore").strip()
                    tmp.unlink(missing_ok=True)
                self._send_json({"path": folder if folder else ""})
            except subprocess.TimeoutExpired:
                self._send_json({"path": "", "error": "Tiempo de espera agotado"})
            except Exception as e:
                self._send_json({"path": "", "error": str(e)})

        elif self.path == "/api/ingest/status":
            self._send_json(_get_ingest_state())

        elif self.path == "/api/ingest/log":
            lines = _read_log_tail(_INGEST_LOG_FILE, 50)
            self._send_json({"lines": lines})

        elif self.path == "/api/status":
            now = datetime.now()

            # Collect all component statuses
            chromadb = _check_chromadb()
            cache = _check_kb_cache()
            knowledge = _check_knowledge_local()
            hooks = _check_hooks()
            metrics = _parse_motor_ia_log()
            state = _check_state()

            # Overall health
            components_ok = sum([
                chromadb["status"] == "OK",
                hooks.get("pre_hook") == "REGISTERED",
                hooks.get("post_hook") == "REGISTERED",
                knowledge["status"] == "OK",
            ])

            if components_ok == 4:
                overall = "HEALTHY"
            elif components_ok >= 2:
                overall = "DEGRADED"
            else:
                overall = "CRITICAL"

            status = {
                "timestamp": now.strftime("%d-%m-%Y %H:%M:%S"),
                "overall_health": overall,
                "components_ok": components_ok,
                "components_total": 4,

                # Component: ChromaDB (KB principal)
                "chromadb": chromadb,

                # Component: Cache TF-IDF
                "cache": cache,

                # Component: Knowledge local (backup)
                "knowledge_local": knowledge,

                # Component: Hooks
                "hooks": hooks,

                # Metrics del día
                "metrics": metrics,

                # Estado actual
                "current_state": state,

                # Log reciente
                "log_tail": _read_log_tail(_PROJECT / "core" / "motor_ia_hook.log", 15),
            }

            self._send_json(status)

        else:
            self.send_response(404)
            self.end_headers()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("DASHBOARD_PORT", "8080"))
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    print(f"Motor_IA Dashboard v2 on {host}:{port}", flush=True)
    srv = ThreadedHTTPServer((host, port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
