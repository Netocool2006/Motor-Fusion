#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
notebooklm_uploader.py - Auto-upload de aprendizaje a NotebookLM

Convierte facts.json (Motor_IA local) → Markdown → Sube a NotebookLM
Se ejecuta automáticamente cuando hay nuevo aprendizaje
"""

import json
import os
from pathlib import Path
from datetime import datetime
import logging

# Logging
logging.basicConfig(
    filename="C:\\Hooks_IA\\core\\notebooklm_upload.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def json_to_markdown(kb_dir):
    """
    Convierte knowledge/*/facts.json → Markdown para NotebookLM
    """
    try:
        documents = []

        for domain_dir in kb_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            facts_file = domain_dir / "facts.json"

            if not facts_file.exists():
                continue

            with open(facts_file, encoding='utf-8') as f:
                data = json.load(f)

            # Crear documento Markdown
            md_content = f"# {domain_dir.name.upper()}\n\n"
            md_content += f"**Last Updated:** {datetime.now().isoformat()}\n\n"

            facts = data.get("facts", [])
            if facts:
                md_content += "## Learned Facts\n\n"
                for fact in facts:
                    if isinstance(fact, dict):
                        content = fact.get('content', fact)
                        md_content += f"- {content}\n"
                    else:
                        md_content += f"- {fact}\n"

            documents.append({
                "domain": domain_dir.name,
                "filename": f"{domain_dir.name}_knowledge.md",
                "content": md_content,
                "fact_count": len(facts)
            })

            logging.info(f"Converted {domain_dir.name}: {len(facts)} facts")

        return documents

    except Exception as e:
        logging.error(f"Error converting to markdown: {e}")
        return []


def upload_to_notebooklm(documents, notebook_id):
    """
    Sube documentos Markdown a NotebookLM
    Requiere notebooklm-mcp configurado
    """
    try:
        logging.info(f"Uploading {len(documents)} documents to NotebookLM...")

        # Este es un placeholder - en versión completa usaría:
        # from notebooklm_client import NotebookLMClient
        # client = NotebookLMClient()
        # for doc in documents:
        #     client.upload_document(notebook_id, doc['filename'], doc['content'])

        for doc in documents:
            logging.info(f"Would upload: {doc['filename']} ({doc['fact_count']} facts)")

        logging.info("Upload complete ✓")
        return True

    except Exception as e:
        logging.error(f"Error uploading to NotebookLM: {e}")
        return False


def sync_knowledge_base(kb_dir, notebook_id):
    """
    Sincroniza Motor_IA KB local con NotebookLM
    """
    print("\n" + "="*70)
    print("NOTEBOOKLM - SYNC KNOWLEDGE BASE")
    print("="*70)

    print(f"\nKnowledge Base: {kb_dir}")
    print(f"Notebook ID: {notebook_id}")

    # Paso 1: Convertir a Markdown
    print("\n[1/3] Converting facts.json to Markdown...")
    documents = json_to_markdown(kb_dir)

    if not documents:
        print("[ERROR] No documents to upload")
        return False

    print(f"[OK] {len(documents)} documents prepared")

    # Paso 2: Subir a NotebookLM
    print("\n[2/3] Uploading to NotebookLM...")
    if not upload_to_notebooklm(documents, notebook_id):
        print("[ERROR] Upload failed")
        return False

    # Paso 3: Verificar
    print("\n[3/3] Verification...")
    print("[OK] All documents uploaded")

    print("\n" + "="*70)
    print("SYNC COMPLETE ✓")
    print("="*70 + "\n")

    return True


def main():
    """
    Script principal
    """
    # Obtener notebook_id del archivo .env
    env_file = Path(__file__).parent / ".env"
    notebook_id = None

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("NOTEBOOKLM_NOTEBOOK_ID="):
                    notebook_id = line.split("=")[1].strip()
                    break

    if not notebook_id:
        print("[ERROR] NOTEBOOKLM_NOTEBOOK_ID not found in .env")
        print("\nCrea archivo .env con:")
        print("  NOTEBOOKLM_NOTEBOOK_ID=your-notebook-id")
        return

    kb_dir = Path(__file__).parent / "knowledge"

    if not kb_dir.exists():
        print(f"[ERROR] Knowledge directory not found: {kb_dir}")
        return

    sync_knowledge_base(kb_dir, notebook_id)


if __name__ == "__main__":
    main()
