#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
vector_kb.py - RAG propio: Embeddings + ChromaDB + Retrieval
=============================================================
Reemplazo directo de notebooklm_kb.py.
Misma interfaz: ask_kb(query) y save_to_kb(query, answer, source)
Sin límites diarios, instantáneo, offline.

Stack:
  - Embeddings: sentence-transformers (all-MiniLM-L6-v2)
  - Vector DB: ChromaDB (local, persistente)
  - Retrieval: cosine similarity top-k
"""

import json
import logging
import unicodedata
from pathlib import Path
from datetime import datetime

log = logging.getLogger("vector_kb")

_PROJECT = Path(__file__).resolve().parent.parent
_CHROMA_DIR = _PROJECT / "core" / "chroma_db"
_KNOWLEDGE_DIR = _PROJECT / "knowledge"

# Globals (lazy init)
_client = None
_collection = None
_embedder = None


def _get_embedder():
    """Carga el modelo de embeddings (una sola vez, silencioso)."""
    global _embedder
    if _embedder is None:
        import os
        import sys
        import warnings
        # Silenciar TODA la salida del modelo
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
        warnings.filterwarnings("ignore")
        _real_stdout = sys.stdout
        _real_stderr = sys.stderr
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        finally:
            sys.stdout.close()
            sys.stderr.close()
            sys.stdout = _real_stdout
            sys.stderr = _real_stderr
        log.info("Embedder loaded: all-MiniLM-L6-v2")
    return _embedder


def _get_collection():
    """Obtiene la colección de ChromaDB (crea si no existe)."""
    global _client, _collection
    if _collection is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            name="motor_ia_kb",
            metadata={"hnsw:space": "cosine"},
        )
        log.info(f"ChromaDB collection: {_collection.count()} documents")
    return _collection


def _normalize(text):
    """Normaliza texto: quita acentos, lowercase."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower().strip()


def ask_kb(query):
    """
    Busca en el KB vectorial (ChromaDB).
    Interfaz idéntica a notebooklm_kb.ask_kb().

    Returns:
        dict con:
          - answer: str
          - found: bool
          - source: "vector_kb"
          - raw: None (compatibilidad)
          - similarity: float (0-1)
          - sources_used: int (cuántos chunks contribuyeron)
    """
    try:
        collection = _get_collection()

        if collection.count() == 0:
            log.info("Vector KB empty, no results")
            return {"answer": "", "raw": None, "found": False, "source": "vector_kb"}

        embedder = _get_embedder()
        query_embedding = embedder.encode([query], show_progress_bar=False).tolist()

        # Buscar top-5 documentos más similares
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(5, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"] or not results["documents"][0]:
            return {"answer": "", "raw": None, "found": False, "source": "vector_kb"}

        # Filtrar por similitud + coherencia entre resultados
        docs = results["documents"][0]
        distances = results["distances"][0]
        metadatas = results["metadatas"][0]

        # Calcular similitud del mejor resultado
        best_sim = 1 - distances[0] if distances else 0

        # Si el mejor resultado tiene baja similitud Y los top-3 son de
        # dominios diferentes, probablemente no es relevante (ruido)
        if best_sim < 0.50 and len(distances) >= 3:
            top3_domains = set(m.get("domain", "") for m in metadatas[:3])
            if len(top3_domains) >= 3:
                # Resultados dispersos = no hay conocimiento real
                log.info(f"Vector KB: low confidence (sim={best_sim:.3f}, scattered domains={top3_domains})")
                return {"answer": "", "raw": None, "found": False, "source": "vector_kb"}

        relevant = []
        for doc, dist, meta in zip(docs, distances, metadatas):
            similarity = 1 - dist
            if similarity > 0.40:
                relevant.append({
                    "text": doc,
                    "similarity": similarity,
                    "domain": meta.get("domain", "unknown"),
                    "type": meta.get("type", "unknown"),
                })

        if not relevant:
            log.info(f"Vector KB: no relevant results (best dist={distances[0]:.3f})")
            return {"answer": "", "raw": None, "found": False, "source": "vector_kb"}

        # Armar respuesta consolidada de los chunks relevantes
        answer_parts = []
        for r in relevant:
            answer_parts.append(r["text"])

        answer = "\n\n".join(answer_parts[:3])  # Top 3 chunks

        best_sim = relevant[0]["similarity"]
        log.info(
            f"Vector KB: found {len(relevant)} relevant chunks, "
            f"best_sim={best_sim:.3f}, domains={set(r['domain'] for r in relevant)}"
        )

        return {
            "answer": answer,
            "raw": None,
            "found": True,
            "source": "vector_kb",
            "similarity": best_sim,
            "sources_used": len(relevant),
        }

    except Exception as e:
        log.error(f"Vector KB ask error: {e}")
        return {"answer": "", "raw": None, "found": False, "source": "vector_kb_error"}


def save_to_kb(query, answer, source="ML"):
    """
    Guarda conocimiento nuevo en ChromaDB.
    Interfaz idéntica a notebooklm_kb.save_to_kb().
    """
    try:
        collection = _get_collection()
        embedder = _get_embedder()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc_id = f"learned_{int(datetime.now().timestamp())}"

        # El documento es la pregunta + respuesta
        full_text = f"Pregunta: {query}\nRespuesta: {answer}"

        embedding = embedder.encode([full_text], show_progress_bar=False).tolist()

        collection.add(
            ids=[doc_id],
            embeddings=embedding,
            documents=[full_text],
            metadatas=[{
                "query": query[:200],
                "source": source,
                "type": "learned",
                "domain": "auto_learned",
                "timestamp": timestamp,
            }],
        )

        log.info(f"Vector KB saved: '{query[:50]}' as {doc_id}")
        return doc_id

    except Exception as e:
        log.error(f"Vector KB save error: {e}")
        return None


def save_session_summary(summary):
    """
    Guarda resumen de sesión para continuidad entre sesiones.
    """
    try:
        collection = _get_collection()
        embedder = _get_embedder()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc_id = f"session_{int(datetime.now().timestamp())}"

        embedding = embedder.encode([summary], show_progress_bar=False).tolist()

        collection.add(
            ids=[doc_id],
            embeddings=embedding,
            documents=[summary],
            metadatas=[{
                "type": "session_summary",
                "domain": "sessions",
                "timestamp": timestamp,
            }],
        )

        log.info(f"Session summary saved: {doc_id}")
        return doc_id

    except Exception as e:
        log.error(f"Session summary save error: {e}")
        return None


def get_last_session():
    """Recupera el último resumen de sesión."""
    try:
        collection = _get_collection()

        # Buscar por metadato type=session_summary
        results = collection.get(
            where={"type": "session_summary"},
            include=["documents", "metadatas"],
        )

        if not results["documents"]:
            return None

        # Encontrar el más reciente por timestamp
        latest = None
        latest_ts = ""
        for doc, meta in zip(results["documents"], results["metadatas"]):
            ts = meta.get("timestamp", "")
            if ts > latest_ts:
                latest_ts = ts
                latest = doc

        return latest

    except Exception as e:
        log.error(f"Get last session error: {e}")
        return None


def index_knowledge_base():
    """
    Indexa todo el contenido de knowledge/ en ChromaDB.
    Se ejecuta una vez para migrar el KB local.
    """
    collection = _get_collection()
    embedder = _get_embedder()

    indexed = 0
    skipped = 0

    for domain_dir in sorted(_KNOWLEDGE_DIR.iterdir()):
        if not domain_dir.is_dir():
            continue

        domain_name = domain_dir.name

        # Skip test domains
        if any(x in domain_name for x in ["test", "Edit", "Motor", "dominio_que_no"]):
            continue

        # Process facts
        facts_file = domain_dir / "facts.json"
        if facts_file.exists() and facts_file.stat().st_size > 50:
            try:
                with open(facts_file, encoding="utf-8") as f:
                    facts = json.load(f)

                chunks = _extract_chunks_from_facts(facts, domain_name)
                for i, chunk in enumerate(chunks):
                    doc_id = f"kb_{domain_name}_fact_{i}"

                    # Check if already indexed
                    try:
                        existing = collection.get(ids=[doc_id])
                        if existing["ids"]:
                            skipped += 1
                            continue
                    except Exception:
                        pass

                    embedding = embedder.encode([chunk["text"]], show_progress_bar=False).tolist()
                    collection.add(
                        ids=[doc_id],
                        embeddings=embedding,
                        documents=[chunk["text"]],
                        metadatas=[{
                            "domain": domain_name,
                            "type": "fact",
                            "key": chunk.get("key", ""),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }],
                    )
                    indexed += 1

            except Exception as e:
                log.error(f"Error indexing facts for {domain_name}: {e}")

        # Process patterns
        patterns_file = domain_dir / "patterns.json"
        if patterns_file.exists() and patterns_file.stat().st_size > 100:
            try:
                with open(patterns_file, encoding="utf-8") as f:
                    patterns = json.load(f)

                chunks = _extract_chunks_from_patterns(patterns, domain_name)
                for i, chunk in enumerate(chunks):
                    doc_id = f"kb_{domain_name}_pattern_{i}"

                    try:
                        existing = collection.get(ids=[doc_id])
                        if existing["ids"]:
                            skipped += 1
                            continue
                    except Exception:
                        pass

                    embedding = embedder.encode([chunk["text"]], show_progress_bar=False).tolist()
                    collection.add(
                        ids=[doc_id],
                        embeddings=embedding,
                        documents=[chunk["text"]],
                        metadatas=[{
                            "domain": domain_name,
                            "type": "pattern",
                            "key": chunk.get("key", ""),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }],
                    )
                    indexed += 1

            except Exception as e:
                log.error(f"Error indexing patterns for {domain_name}: {e}")

    log.info(f"Indexing complete: {indexed} new, {skipped} already indexed, total={collection.count()}")
    return {"indexed": indexed, "skipped": skipped, "total": collection.count()}


def _extract_chunks_from_facts(facts, domain):
    """Extrae chunks de texto de facts.json para indexar."""
    chunks = []

    if isinstance(facts, dict):
        entries = facts.get("entries", facts)
        for key, val in entries.items():
            if isinstance(val, dict):
                fact = val.get("fact", val)
                if isinstance(fact, dict):
                    text_parts = [f"Dominio: {domain}", f"Clave: {key}"]
                    for fk, fv in fact.items():
                        if isinstance(fv, str) and fv:
                            text_parts.append(f"{fk}: {fv}")
                        elif isinstance(fv, list):
                            text_parts.append(f"{fk}: {', '.join(str(x)[:200] for x in fv[:5])}")
                    text = "\n".join(text_parts)
                    if len(text) > 50:
                        # Chunk if too long
                        for chunk_text in _split_text(text, max_len=1000):
                            chunks.append({"text": chunk_text, "key": key})
                else:
                    text = f"Dominio: {domain}\nClave: {key}\n{str(fact)[:1000]}"
                    chunks.append({"text": text, "key": key})
            elif isinstance(val, str) and len(val) > 20:
                chunks.append({"text": f"Dominio: {domain}\n{key}: {val[:1000]}", "key": key})

    return chunks


def _extract_chunks_from_patterns(patterns, domain):
    """Extrae chunks de texto de patterns.json para indexar."""
    chunks = []

    if isinstance(patterns, dict):
        for key, val in patterns.items():
            if isinstance(val, str) and len(val) > 30:
                for chunk_text in _split_text(f"Dominio: {domain}\nPatrón: {key}\n{val}", max_len=1000):
                    chunks.append({"text": chunk_text, "key": key})
            elif isinstance(val, dict):
                text = f"Dominio: {domain}\nPatrón: {key}\n{json.dumps(val, ensure_ascii=False)[:2000]}"
                for chunk_text in _split_text(text, max_len=1000):
                    chunks.append({"text": chunk_text, "key": key})
            elif isinstance(val, list):
                for i, item in enumerate(val[:10]):
                    text = f"Dominio: {domain}\nPatrón: {key}[{i}]\n{str(item)[:1000]}"
                    if len(text) > 50:
                        chunks.append({"text": text, "key": f"{key}_{i}"})

    return chunks


def _split_text(text, max_len=1000):
    """Divide texto largo en chunks para embedding."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    words = text.split()
    current = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 > max_len and current:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(word)
        current_len += len(word) + 1

    if current:
        chunks.append(" ".join(current))

    return chunks


def get_stats():
    """Estadísticas del KB vectorial."""
    try:
        collection = _get_collection()
        count = collection.count()

        # Count by type
        facts = collection.get(where={"type": "fact"}, include=[])
        patterns = collection.get(where={"type": "pattern"}, include=[])
        learned = collection.get(where={"type": "learned"}, include=[])
        sessions = collection.get(where={"type": "session_summary"}, include=[])

        return {
            "total": count,
            "facts": len(facts["ids"]) if facts["ids"] else 0,
            "patterns": len(patterns["ids"]) if patterns["ids"] else 0,
            "learned": len(learned["ids"]) if learned["ids"] else 0,
            "sessions": len(sessions["ids"]) if sessions["ids"] else 0,
        }
    except Exception as e:
        return {"total": 0, "error": str(e)}


if __name__ == "__main__":
    # CLI: indexar KB
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "index":
        print("Indexando knowledge/ en ChromaDB...")
        result = index_knowledge_base()
        print(f"Listo: {result}")
    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(get_stats())
    elif len(sys.argv) > 1 and sys.argv[1] == "ask":
        query = " ".join(sys.argv[2:])
        result = ask_kb(query)
        print(f"Found: {result['found']}")
        print(f"Source: {result['source']}")
        if result["found"]:
            print(f"Similarity: {result.get('similarity', 'N/A')}")
            print(f"Answer:\n{result['answer'][:500]}")
    else:
        print("Usage: python vector_kb.py [index|stats|ask <query>]")
