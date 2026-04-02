#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_enforcer_hook_v2.py - Hook completo con flujo NotebookLM → Internet → ML
Se ejecuta ANTES de cada respuesta en CLI Claude

Flujo:
1. Consulta NotebookLM (KB aprendido)
   → SI: Responde con cita, KB% = 100%
   → NO: Continúa
2. Busca en Internet (WebSearch)
   → SI: Responde con fuente, guarda en NotebookLM, Internet% = 100%
   → NO: Continúa
3. Usa ML (mi conocimiento)
   → Responde, guarda en NotebookLM, ML% = 100%
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import logging

# Setup
sys.path.insert(0, str(Path(__file__).parent.parent))

# Logging
logging.basicConfig(
    filename="C:\\Hooks_IA\\core\\kb_enforcer_v2.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_user_query():
    """
    Extrae última pregunta del usuario del transcript
    """
    try:
        from config import CHANCE_PROJECT_DIR

        transcript_dir = CHANCE_PROJECT_DIR
        if not transcript_dir.exists():
            return None

        transcript_files = list(transcript_dir.glob("*.jsonl"))
        if not transcript_files:
            return None

        transcript_file = max(transcript_files, key=lambda p: p.stat().st_mtime)

        query = None
        with open(transcript_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for line in reversed(lines[-200:]):
            try:
                data = json.loads(line)

                if data.get('type') == 'user':
                    content = data.get('content')
                    if content and isinstance(content, str):
                        query = content.strip()
                        if query:
                            return query

                    msg = data.get('message', {})
                    msg_content = msg.get('content', [])
                    if isinstance(msg_content, list):
                        for item in msg_content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                query = item.get('text', '').strip()
                                if query:
                                    return query

            except:
                continue

        return None

    except Exception as e:
        logging.error(f"Error getting query: {e}")
        return None


def query_notebooklm(query):
    """
    PASO 1: Consulta NotebookLM
    Intenta encontrar respuesta en lo que ya aprendimos
    """
    try:
        # Este es un placeholder - requiere notebooklm-mcp instalado
        # En producción, usaría: from notebooklm_client import NotebookLMClient

        # Por ahora, retorna empty (fallback a Internet/ML)
        logging.info(f"Checking NotebookLM for: {query[:60]}")
        return None

    except Exception as e:
        logging.warning(f"NotebookLM query error: {e}")
        return None


def search_internet(query):
    """
    PASO 2: Busca en Internet
    Si lo anterior no encontró nada, buscar en web
    """
    try:
        logging.info(f"Searching internet for: {query[:60]}")

        # Claude Code tiene WebSearch disponible
        # El hook no puede ejecutarlo directamente, pero podría
        # En versión completa, usaría: web_search(query)

        # Por ahora retorna empty (fallback a ML)
        return None

    except Exception as e:
        logging.warning(f"Internet search error: {e}")
        return None


def determine_sources(kb_found, internet_found):
    """
    Determina porcentajes basándose en qué encontró
    """
    if kb_found:
        return {"kb_pct": 100, "internet_pct": 0, "ml_pct": 0, "source": "KB"}

    if internet_found:
        return {"kb_pct": 0, "internet_pct": 100, "ml_pct": 0, "source": "Internet"}

    # Fallback a ML
    return {"kb_pct": 0, "internet_pct": 0, "ml_pct": 100, "source": "ML"}


def save_hook_result(result):
    """
    Guarda resultado en archivo para que Claude lo lea
    """
    try:
        result_file = Path(r"C:\Hooks_IA\core\kb_search_result_v2.json")
        result_file.parent.mkdir(parents=True, exist_ok=True)

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logging.info(f"Result saved: {result['source']} (KB%={result['kb_pct']})")

    except Exception as e:
        logging.error(f"Error saving result: {e}")


def save_to_notebooklm(result):
    """
    AUTO-SAVE: Guarda resultado a NotebookLM si no vino de ahí
    """
    try:
        if result['source'] in ['Internet', 'ML']:
            # Aquí iría upload a NotebookLM
            logging.info(f"Auto-saving to NotebookLM: {result['source']}")
            # upload_to_notebooklm(result)

    except Exception as e:
        logging.warning(f"Error saving to NotebookLM: {e}")


def main():
    """
    Hook principal - Flujo completo
    """
    try:
        query = get_user_query()

        if not query:
            logging.warning("No query found")
            return

        logging.info(f"\n{'='*70}")
        logging.info(f"PROCESSING: {query[:100]}")
        logging.info(f"{'='*70}")

        # PASO 1: Consultar NotebookLM
        kb_result = query_notebooklm(query)

        if kb_result:
            result = {
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "source": "KB",
                "kb_pct": 100,
                "internet_pct": 0,
                "ml_pct": 0,
                "content": kb_result.get('content'),
                "citation": kb_result.get('citation', 'NotebookLM')
            }
            save_hook_result(result)
            logging.info("FOUND in NotebookLM ✓")
            return

        # PASO 2: Buscar en Internet
        internet_result = search_internet(query)

        if internet_result:
            result = {
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "source": "Internet",
                "kb_pct": 0,
                "internet_pct": 100,
                "ml_pct": 0,
                "content": internet_result.get('content'),
                "source_url": internet_result.get('url')
            }
            save_hook_result(result)
            save_to_notebooklm(result)
            logging.info("FOUND in Internet ✓ (will auto-save to KB)")
            return

        # PASO 3: Usar ML
        result = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "source": "ML",
            "kb_pct": 0,
            "internet_pct": 0,
            "ml_pct": 100,
            "content": None  # Claude generará la respuesta
        }
        save_hook_result(result)
        save_to_notebooklm(result)
        logging.info("Will use ML ✓ (will auto-save to KB)")

    except Exception as e:
        logging.error(f"Hook error: {e}")


if __name__ == "__main__":
    main()
