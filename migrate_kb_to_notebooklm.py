#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
migrate_kb_to_notebooklm.py - Sube KB local a NotebookLM DIRECTO
=================================================================
Lee facts.json + patterns.json de cada dominio, los convierte a
Markdown legible, y los sube como sources a NotebookLM via API.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT))

KB_DIR = _PROJECT / "knowledge"
MAX_SOURCE_CHARS = 400000  # Safe limit per source

# Dominios a subir (orden por prioridad)
UPLOAD_DOMAINS = [
    "business_rules",
    "sap_tierra",
    "sap_automation",
    "sap_cloud",
    "sow",
    "outlook",
    "general",
    "catalog",
    "monday_automation",
    "monday",
    "web_forms",
    "claude_chrome",
    "bom",
    "sap_js_internals",
    "clients",
    "bpm_bau",
    "contabilidad",
    "finanzas",
    "pptx",
]

# Skip: files (5MB session data), sessions (logs), test domains


def load_domain_content(domain_name):
    """Lee facts + patterns de un dominio y los convierte a Markdown."""
    domain_dir = KB_DIR / domain_name
    if not domain_dir.exists():
        return None

    parts = [
        f"# Dominio: {domain_name}",
        f"Migrado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # === FACTS ===
    facts_file = domain_dir / "facts.json"
    if facts_file.exists() and facts_file.stat().st_size > 10:
        try:
            with open(facts_file, encoding="utf-8") as f:
                facts = json.load(f)

            if isinstance(facts, dict):
                entries = facts.get("entries", facts)
                desc = facts.get("description", "")
                if desc:
                    parts.append(f"**Descripción:** {desc}\n")

                parts.append(f"## Hechos ({len(entries)} entradas)")
                parts.append("")

                for key, val in entries.items():
                    if isinstance(val, dict):
                        fact = val.get("fact", val)
                        rule = fact.get("rule", "") if isinstance(fact, dict) else str(fact)
                        parts.append(f"### {key}")
                        if isinstance(fact, dict):
                            for fk, fv in fact.items():
                                if isinstance(fv, str) and fv:
                                    parts.append(f"- **{fk}:** {fv[:1000]}")
                                elif isinstance(fv, list) and fv:
                                    parts.append(f"- **{fk}:**")
                                    for item in fv[:10]:
                                        parts.append(f"  - {str(item)[:500]}")
                        else:
                            parts.append(str(fact)[:2000])
                        parts.append("")
                    else:
                        parts.append(f"- **{key}**: {str(val)[:1000]}")

            elif isinstance(facts, list):
                parts.append(f"## Hechos ({len(facts)} entradas)")
                for item in facts[:50]:
                    parts.append(f"- {str(item)[:1000]}")
            parts.append("")
        except Exception as e:
            parts.append(f"<!-- Error en facts: {e} -->")

    # === PATTERNS ===
    patterns_file = domain_dir / "patterns.json"
    if patterns_file.exists() and patterns_file.stat().st_size > 100:
        try:
            with open(patterns_file, encoding="utf-8") as f:
                patterns = json.load(f)

            if isinstance(patterns, dict):
                parts.append(f"## Patrones")
                parts.append("")
                for key, val in patterns.items():
                    parts.append(f"### {key}")
                    if isinstance(val, str):
                        parts.append(val[:3000])
                    elif isinstance(val, list):
                        for item in val[:15]:
                            parts.append(f"- {str(item)[:1000]}")
                    elif isinstance(val, dict):
                        txt = json.dumps(val, ensure_ascii=False, indent=2)
                        parts.append(txt[:5000])
                    parts.append("")

            elif isinstance(patterns, list):
                parts.append(f"## Patrones ({len(patterns)} entradas)")
                for item in patterns[:30]:
                    if isinstance(item, dict):
                        txt = json.dumps(item, ensure_ascii=False, indent=2)
                        parts.append(txt[:2000])
                    else:
                        parts.append(f"- {str(item)[:1000]}")
                    parts.append("")
        except Exception as e:
            parts.append(f"<!-- Error en patterns: {e} -->")

    content = "\n".join(parts)

    # Truncate if too big
    if len(content) > MAX_SOURCE_CHARS:
        content = content[:MAX_SOURCE_CHARS] + "\n\n<!-- TRUNCADO: contenido excedía límite -->"

    return content if len(content) > 100 else None


def load_playbooks():
    """Consolida SAP playbooks en un solo source."""
    pb_dir = KB_DIR / "sap_js_internals" / "playbooks"
    if not pb_dir.exists():
        return None

    parts = [
        "# SAP Playbooks Consolidados",
        f"Migrado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for pb_file in sorted(pb_dir.glob("*.json")):
        if pb_file.name.startswith("_"):
            continue
        try:
            with open(pb_file, encoding="utf-8") as f:
                pb = json.load(f)
            parts.append(f"## {pb_file.stem}")
            txt = json.dumps(pb, ensure_ascii=False, indent=2)
            parts.append(txt[:10000])
            parts.append("")
        except Exception:
            pass

    content = "\n".join(parts)
    if len(content) > MAX_SOURCE_CHARS:
        content = content[:MAX_SOURCE_CHARS] + "\n\n<!-- TRUNCADO -->"
    return content if len(content) > 100 else None


async def upload_with_retry(client, notebook_id, title, content, max_retries=3):
    """Sube source con retry para rate limiting."""
    for attempt in range(max_retries):
        try:
            source = await client.sources.add_text(
                notebook_id, title, content, wait=True, wait_timeout=60.0
            )
            return getattr(source, "id", str(source))
        except Exception as e:
            err = str(e).lower()
            if "rate" in err or "429" in err or "rejected" in err:
                wait = 8 * (attempt + 1)
                print(f" rate-limited, waiting {wait}s...", end="", flush=True)
                await asyncio.sleep(wait)
            else:
                print(f" ERROR: {e}")
                return None
    return None


async def main():
    from core.notebooklm_kb import _get_client, _load_notebook_id

    notebook_id = _load_notebook_id()
    print(f"Notebook: {notebook_id}")

    client = await _get_client()
    try:
        # Check existing sources
        existing = await client.sources.list(notebook_id)
        existing_titles = {getattr(s, "title", ""): getattr(s, "id", "") for s in existing}
        slots_left = 50 - len(existing)

        print(f"Sources actuales: {len(existing)}")
        print(f"Slots disponibles: {slots_left}")
        print()

        if slots_left < 5:
            print("ADVERTENCIA: Pocos slots disponibles. Subiendo solo los más importantes.")

        uploaded = 0
        skipped = 0
        failed = 0

        # Upload each domain
        for domain in UPLOAD_DOMAINS:
            if uploaded >= slots_left - 1:  # Leave 1 for playbooks
                print(f"[LIMIT] No hay más slots, deteniendo.")
                break

            title = f"KB: {domain}"

            if title in existing_titles:
                print(f"[SKIP] {title} (ya existe)")
                skipped += 1
                continue

            content = load_domain_content(domain)
            if not content:
                print(f"[SKIP] {title} (sin contenido)")
                skipped += 1
                continue

            size_kb = len(content) / 1024
            print(f"[UPLOAD] {title} ({size_kb:.0f} KB)...", end=" ", flush=True)

            source_id = await upload_with_retry(client, notebook_id, title, content)

            if source_id:
                print(f"OK [{source_id[:10]}]")
                uploaded += 1
            else:
                print("FAILED")
                failed += 1

            await asyncio.sleep(4)  # Rate limit prevention

        # Upload playbooks
        pb_title = "KB: sap_playbooks"
        if pb_title not in existing_titles and uploaded < slots_left:
            pb_content = load_playbooks()
            if pb_content:
                size_kb = len(pb_content) / 1024
                print(f"[UPLOAD] {pb_title} ({size_kb:.0f} KB)...", end=" ", flush=True)
                source_id = await upload_with_retry(client, notebook_id, pb_title, pb_content)
                if source_id:
                    print(f"OK [{source_id[:10]}]")
                    uploaded += 1
                else:
                    print("FAILED")
                    failed += 1

        # Summary
        print()
        print(f"{'='*50}")
        print(f"MIGRACIÓN COMPLETADA")
        print(f"  Subidos:  {uploaded}")
        print(f"  Saltados: {skipped}")
        print(f"  Fallidos: {failed}")
        print(f"  Sources totales: {len(existing) + uploaded}")
        print(f"{'='*50}")

    finally:
        await client.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
