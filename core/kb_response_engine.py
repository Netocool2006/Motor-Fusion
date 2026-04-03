#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_response_engine.py
======================
Motor que OBLIGA el protocolo KB → Internet → ML antes de responder.
Debe ejecutarse SIEMPRE antes de una respuesta.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Importar search_protocol - manejar ambos tipos de import
try:
    from .search_protocol import (
        search_kb,
        calculate_coverage,
        build_source_footer,
        detect_domain,
        save_to_kb,
        should_save_to_kb
    )
except ImportError:
    # Fallback para import absoluto
    sys.path.insert(0, str(Path(__file__).parent))
    from search_protocol import (
        search_kb,
        calculate_coverage,
        build_source_footer,
        detect_domain,
        save_to_kb,
        should_save_to_kb
    )


class KBResponseEngine:
    """
    Motor de respuesta que requiere búsqueda en KB primero.
    Uso:
        engine = KBResponseEngine("Tu pregunta aquí")
        result = engine.process()
        print(result['response'])
        print(result['sources_footer'])
    """

    def __init__(self, query: str):
        """
        Inicializa el motor con una pregunta.
        """
        self.query = query
        self.domain = detect_domain(query)
        self.kb_results = []
        self.kb_pct = 0
        self.internet_pct = 0
        self.ml_pct = 0
        self.sources_footer = ""
        self.should_save = False
        self.save_result = None

    def search_kb(self) -> dict:
        """
        Paso 1: Busca en KB local.
        Retorna % de cobertura encontrada.
        """
        self.kb_results = search_kb(self.query, self.domain, limit=10)

        if not self.kb_results:
            self.kb_pct = 0
            return {
                "found": False,
                "coverage": 0,
                "results": []
            }

        # Coverage basado en cantidad de resultados
        self.kb_pct = min(100, 30 + len(self.kb_results) * 15)

        return {
            "found": True,
            "coverage": self.kb_pct,
            "results": self.kb_results,
            "domain": self.domain
        }

    def calculate_percentages(self) -> dict:
        """
        Paso 2: Calcula distribuación KB → Internet → ML para sumar 100%.
        """
        if self.kb_pct >= 100:
            # Toda la respuesta viene de KB
            self.kb_pct = 100
            self.internet_pct = 0
            self.ml_pct = 0
        elif self.kb_pct >= 80:
            # KB bueno, Internet complementa
            self.internet_pct = 100 - self.kb_pct
            self.ml_pct = 0
        elif self.kb_pct >= 50:
            # KB parcial, Internet + ML
            remaining = 100 - self.kb_pct
            self.internet_pct = remaining // 2
            self.ml_pct = remaining - self.internet_pct
        elif self.kb_pct > 0:
            # KB muy poco, Internet principal, ML complementa
            self.internet_pct = 60
            self.ml_pct = 40 - self.kb_pct
        else:
            # Sin KB, Internet + ML
            self.internet_pct = 60
            self.ml_pct = 40

        # Validar que sume exactamente 100
        total = self.kb_pct + self.internet_pct + self.ml_pct
        if total != 100:
            # Ajustar ML
            self.ml_pct = 100 - self.kb_pct - self.internet_pct

        return {
            "kb_pct": self.kb_pct,
            "internet_pct": self.internet_pct,
            "ml_pct": self.ml_pct,
            "total": self.kb_pct + self.internet_pct + self.ml_pct
        }

    def build_sources(self) -> str:
        """
        Paso 3: Construye footer de fuentes.
        """
        self.sources_footer = build_source_footer(
            self.kb_pct,
            self.internet_pct,
            self.ml_pct
        )
        return self.sources_footer

    def check_auto_save(self) -> dict:
        """
        Paso 4: Determina si debería guardarse automáticamente en KB.
        Regla: Si KB_pct == 0 Y (internet_pct > 0 OR ml_pct > 0) → guardar
        """
        self.should_save = should_save_to_kb(
            self.kb_pct,
            self.internet_pct,
            self.ml_pct
        )
        return {
            "should_save": self.should_save,
            "condition": "KB=0% && (Internet>0 OR ML>0)"
        }

    def process(self, user_response: str = None) -> dict:
        """
        Ejecuta el pipeline COMPLETO:
        1. Busca KB
        2. Calcula percentajes
        3. Construye footer
        4. Valida auto-save

        Args:
            user_response: La respuesta que el usuario está dando (para guardar si aplica)

        Returns:
            {
                "query": str,
                "domain": str,
                "kb_results": list,
                "kb_pct": int,
                "internet_pct": int,
                "ml_pct": int,
                "sources_footer": str,
                "should_save": bool,
                "save_result": dict or None,
                "timestamp": str
            }
        """
        # Paso 1: Buscar en KB
        kb_search = self.search_kb()

        # Paso 2: Calcular percentajes
        percentages = self.calculate_percentages()

        # Paso 3: Construir footer de fuentes
        footer = self.build_sources()

        # Paso 4: Validar auto-save
        auto_save = self.check_auto_save()

        # Paso 5: Si aplica, guardar automáticamente
        if self.should_save and user_response:
            self.save_result = save_to_kb(self.query, user_response, self.domain)

        result = {
            "query": self.query,
            "domain": self.domain,
            "kb_found": len(self.kb_results),
            "kb_results": self.kb_results[:3],  # Top 3
            "kb_pct": self.kb_pct,
            "internet_pct": self.internet_pct,
            "ml_pct": self.ml_pct,
            "sources_footer": self.sources_footer,
            "should_save": self.should_save,
            "save_result": self.save_result,
            "timestamp": datetime.now().isoformat(),
            "status": "ready_to_respond"
        }

        return result

    def log_to_file(self, result: dict) -> str:
        """
        Guarda el resultado en KB_responses.log para auditoría.
        """
        log_file = Path(__file__).resolve().parent / "kb_responses.log"

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": self.query,
            "domain": self.domain,
            "kb_pct": self.kb_pct,
            "internet_pct": self.internet_pct,
            "ml_pct": self.ml_pct,
            "kb_found": len(self.kb_results),
            "saved_to_kb": self.should_save
        }

        try:
            # Append JSON line
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            return str(log_file)
        except Exception as e:
            return f"Log error: {str(e)}"


def process_query_with_kb(query: str, user_response: str = None) -> dict:
    """
    Función simple para usar el motor.

    Ejemplo:
        result = process_query_with_kb("¿Cómo usar SAP?", "La respuesta es...")
        print(result['sources_footer'])
    """
    engine = KBResponseEngine(query)
    result = engine.process(user_response)
    engine.log_to_file(result)
    return result


if __name__ == "__main__":
    # Test 1: Pregunta sobre SAP
    print("=== Test 1: Pregunta SAP ===")
    result = process_query_with_kb(
        "¿Cómo configurar una oportunidad en SAP Tierra?",
        "En SAP Tierra, las oportunidades se crean desde el menú CRM..."
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Test 2: Pregunta genérica (sin KB)
    print("\n=== Test 2: Pregunta genérica ===")
    result = process_query_with_kb(
        "¿Cuál es la capital de Francia?",
        "La capital de Francia es París..."
    )
    print(f"Sources: {result['sources_footer']}")
    print(f"Should save: {result['should_save']}")
