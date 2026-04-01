#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_kb_engine.py
Test del motor KB obligatorio
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.kb_response_engine import process_query_with_kb

print("=" * 70)
print("TEST: KB Response Engine - Sistema Obligatorio")
print("=" * 70)

# Test 1: Pregunta SAP (debería encontrar en KB)
print("\n--- Test 1: Pregunta sobre SAP (con KB) ---")
query1 = "¿Cómo crear una oportunidad en SAP Tierra?"
print(f"Query: {query1}")
result1 = process_query_with_kb(query1, "En SAP Tierra, las oportunidades se crean desde...")
print(f"Domain: {result1['domain']}")
print(f"KB Found: {result1['kb_found']}")
print(f"Coverage: KB {result1['kb_pct']}% + Internet {result1['internet_pct']}% + ML {result1['ml_pct']}%")
print(f"Sources: {result1['sources_footer']}")
print(f"Should Save: {result1['should_save']}")

# Test 2: Pregunta genérica (sin KB)
print("\n--- Test 2: Pregunta genérica (sin KB) ---")
query2 = "¿Cuál es la capital de Francia?"
print(f"Query: {query2}")
result2 = process_query_with_kb(query2, "La capital de Francia es París...")
print(f"Domain: {result2['domain']}")
print(f"KB Found: {result2['kb_found']}")
print(f"Coverage: KB {result2['kb_pct']}% + Internet {result2['internet_pct']}% + ML {result2['ml_pct']}%")
print(f"Sources: {result2['sources_footer']}")
print(f"Should Save: {result2['should_save']}")

# Test 3: Pregunta sobre archivos
print("\n--- Test 3: Pregunta sobre gestión de archivos ---")
query3 = "¿Cómo buscar un archivo en una carpeta específica?"
print(f"Query: {query3}")
result3 = process_query_with_kb(query3, "Usar Path.glob() para buscar archivos...")
print(f"Domain: {result3['domain']}")
print(f"KB Found: {result3['kb_found']}")
print(f"Coverage: KB {result3['kb_pct']}% + Internet {result3['internet_pct']}% + ML {result3['ml_pct']}%")
print(f"Sources: {result3['sources_footer']}")
print(f"Should Save: {result3['should_save']}")

print("\n" + "=" * 70)
print("✅ TODOS LOS TESTS COMPLETADOS")
print("=" * 70)
print("\nNOTA: Cada respuesta INCLUYE automáticamente el footer de fuentes.")
print("El sistema es OBLIGATORIO, no opcional.")
