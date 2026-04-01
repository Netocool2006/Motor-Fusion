"""
domains_config.py -- Configuracion de dominios GBM (Solution Advisor)
=====================================================================
NOTA: Estos dominios son ESPECIFICOS de GBM Guatemala y se cargan
via preset ("solution_advisor_gbm"), NO por defecto.

Ver core/domain_presets.py para el sistema de presets.
El motor arranca SIN dominios; se crean dinamicamente segun uso
o al aplicar un preset.

Este archivo mantiene:
  - DOMAINS: dict con la config detallada de cada dominio GBM
    (file, entry_type, tasks) -- usado por task routing
  - TASK_DEPENDENCIES: dependencias cross-domain para tareas
  - get_domains_for_task(): resolucion de dominios para una tarea
  - describe_task(): descripcion legible de tareas
  - is_preset_loaded(): verifica si los dominios GBM estan en domains.json
"""

import json
from config import DOMAINS_FILE

DOMAINS = {
    # ==============================================================
    #  CAPA 1: INTELIGENCIA DOCUMENTAL
    # ==============================================================

    "sow": {
        "description": (
            "Todo sobre SOWs: generacion desde BoM, revision (contradicciones, fechas, "
            "montos, ambiguedades, incoherencias), fusion de multiples SOWs (hasta 6 practicas), "
            "tipos (Renovacion, Proyecto, Bolsa, RFP, Celula), estructura estandar GBM"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "sow_generate",       # Crear SOW desde BoM + plantilla
            "sow_review",         # Detectar errores, contradicciones, incoherencias
            "sow_fusion",         # Mezclar 2-6 SOWs de distintas practicas
            "sow_economic",       # Propuesta economica (ajuste precio, MEP, pagos)
        ],
    },

    "bom": {
        "description": (
            "Bills of Materials: validacion matematica, numeros de parte, "
            "clasificacion (servicio/licencia/software/hardware/hibrido), tipo de cambio, "
            "fusion de multiples BoMs, formato Excel 8 hojas GBM, estrategia de pricing"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "bom_validate",       # Verificar math, part numbers, clasificacion
            "bom_fusion",         # Consolidar N BoMs en uno
            "bom_to_proposal",    # Transformar BoM -> propuesta economica
            "bom_fx_strategy",    # Analisis de tipo de cambio, MEP vs lista
            "bom_payment_split",  # Dividir pagos (ej: 12 meses -> 5 pagos)
        ],
    },

    "pptx": {
        "description": (
            "Presentaciones PowerPoint: resumen de propuestas para cliente, "
            "ofrecimiento de productos/servicios GBM, decks ejecutivos"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "pptx_proposal_summary",  # Deck resumen de propuesta
            "pptx_product_offering",  # Presentacion de producto/servicio
        ],
    },

    # ==============================================================
    #  CAPA 2: AUTOMATIZACION DE SISTEMAS
    # ==============================================================

    "sap_tierra": {
        "description": (
            "SAP CRM Web (Tierra): quotes (manual, contrato, estandar), "
            "items en oportunidades, piezas, licencias, costos, servicios de "
            "soporte/asistencia/asesoria. Automatizacion con Python/Playwright"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "sap_login",              # Login CRM WebUI
            "sap_quote_manual",       # Quote manual
            "sap_quote_contrato",     # Quote de contrato
            "sap_quote_estandar",     # Quote estandar
            "sap_fill_items",         # Llenar items en oportunidad
            "sap_attach_file",        # Adjuntar PDF/correo en SAP
            "sap_navigate_frames",    # Navegacion iFrames
        ],
    },

    "sap_nube": {
        "description": (
            "SAP CRM Nube: version cloud del CRM, formularios, "
            "oportunidades. Diferente interfaz que Tierra"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "sap_nube_quote",
            "sap_nube_items",
            "sap_nube_navigation",
        ],
    },

    "monday": {
        "description": (
            "Monday.com: seguimiento de propuestas, etapas, costos, "
            "valores de venta, criticidad, detalle producto/servicio, "
            "bitacora diaria de actividades"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "monday_update_pipeline",   # Actualizar estado propuesta
            "monday_log_activity",      # Bitacora de actividad
            "monday_import_data",       # Importar datos
        ],
    },

    "bpm_bau": {
        "description": (
            "BPM BAU: disparar procesos, llenar forms y pestanas, "
            "iniciar procesos de autorizacion"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "bau_start_process",
            "bau_fill_form",
            "bau_approval_flow",
        ],
    },

    "outlook": {
        "description": (
            "Outlook: enviar correos, guardar correos como adjuntos, "
            "attachar correos en SAP, adjuntar PDFs en SAP"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "outlook_send",
            "outlook_save_as_attachment",
            "outlook_to_sap",
        ],
    },

    "files": {
        "description": (
            "Manejo de archivos multi-formato: PDF, Excel, TXT, DOCX, JPG, PPTX. "
            "Conversiones, extraccion, OCR, merge"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "file_convert",
            "file_extract_text",
            "file_merge_pdfs",
        ],
    },

    # ==============================================================
    #  CAPA 3: CONOCIMIENTO Y SESIONES
    # ==============================================================

    "sessions": {
        "description": (
            "Sesiones y reuniones: seguimiento cliente (upsell, extensiones), "
            "alineamiento interno (preventa, AMs, delivery), "
            "aprendizaje de nuevos productos/servicios"
        ),
        "file": "facts.json",
        "entry_type": "fact",
        "tasks": [
            "session_client_followup",     # Captura insights cliente
            "session_internal_alignment",   # Sesiones internas
            "session_product_learning",     # Nuevos productos/servicios
        ],
    },

    # ==============================================================
    #  TRANSVERSALES (aplican a todo)
    # ==============================================================

    "business_rules": {
        "description": (
            "Reglas de negocio GBM: nomenclatura codigos (_PS, _RN), "
            "tarifas estandar, clausulas contractuales, SLAs, procesos internos, "
            "convenciones de pricing, IVA, tipos de quote"
        ),
        "file": "facts.json",
        "entry_type": "fact",
        "tasks": [],  # Se consulta desde cualquier otro dominio
    },

    "catalog": {
        "description": (
            "Catalogo de productos y servicios: IBM (DB2, WAS, MQ, Instana), "
            "SAP licencias, servicios GBM (soporte, asistencia, asesoria, "
            "celula desarrollo), codigos, precios, relaciones entre SKUs"
        ),
        "file": "facts.json",
        "entry_type": "fact",
        "tasks": [],
    },
}


# -- Mapeo de tareas a dominios que se deben consultar ----------------
# Cuando ejecutas una tarea, estos son los dominios ADICIONALES
# que se deben consultar automaticamente (cross-domain)

TASK_DEPENDENCIES = {
    # SOW tasks necesitan reglas de negocio + catalogo
    "sow_generate":     ["business_rules", "catalog", "bom"],
    "sow_review":       ["business_rules", "catalog"],
    "sow_fusion":       ["business_rules", "sow"],
    "sow_economic":     ["business_rules", "catalog", "bom"],

    # BoM tasks necesitan catalogo + reglas
    "bom_validate":     ["business_rules", "catalog"],
    "bom_fusion":       ["business_rules", "catalog"],
    "bom_to_proposal":  ["business_rules", "catalog", "sow"],
    "bom_fx_strategy":  ["business_rules"],
    "bom_payment_split": ["business_rules"],

    # SAP tasks necesitan reglas de negocio (nomenclatura, tipos de quote)
    "sap_fill_items":       ["business_rules", "catalog"],
    "sap_quote_manual":     ["business_rules"],
    "sap_quote_contrato":   ["business_rules", "catalog"],
    "sap_quote_estandar":   ["business_rules"],
    "sap_attach_file":      ["outlook", "files"],

    # Monday necesita contexto de propuestas
    "monday_update_pipeline": ["business_rules"],

    # Sesiones alimentan todo
    "session_client_followup":   ["catalog", "business_rules"],
    "session_product_learning":  ["catalog"],
}


def get_domains_for_task(task: str) -> list[str]:
    """
    Dado un task_id, retorna la lista de dominios que hay que consultar.
    Incluye el dominio propio + dependencias.
    """
    # Encontrar dominio primario de la tarea
    primary = None
    for domain, config in DOMAINS.items():
        if task in config.get("tasks", []):
            primary = domain
            break

    if not primary:
        return list(DOMAINS.keys())  # Si no encuentra, buscar en todo

    # Dominio primario + dependencias
    deps = TASK_DEPENDENCIES.get(task, [])
    all_domains = [primary] + [d for d in deps if d != primary]
    return all_domains


def describe_task(task: str) -> str:
    """Genera descripcion legible de una tarea para el prompt."""
    descriptions = {
        "sow_generate": "Generar SOW desde BoM y plantilla GBM",
        "sow_review": "Revisar SOW: contradicciones, fechas, montos, ambiguedades, incoherencias",
        "sow_fusion": "Fusionar multiples SOWs (hasta 6 practicas) en uno solo",
        "sow_economic": "Construir propuesta economica desde BoM (ajuste precio, MEP, pagos)",
        "bom_validate": "Validar BoM: matematica, part numbers, clasificacion, tipo de cambio",
        "bom_fusion": "Consolidar multiples BoMs en uno solo",
        "bom_to_proposal": "Transformar BoM -> propuesta economica con analisis de pricing",
        "bom_fx_strategy": "Analizar estrategia de tipo de cambio",
        "bom_payment_split": "Reestructurar pagos (ej: mensual -> trimestral)",
        "sap_login": "Login en SAP CRM WebUI",
        "sap_fill_items": "Llenar items en oportunidad SAP (piezas, licencias, costos)",
        "sap_quote_manual": "Crear quote manual en SAP CRM",
        "sap_quote_contrato": "Crear quote de contrato en SAP CRM",
        "sap_quote_estandar": "Crear quote estandar en SAP CRM",
        "sap_attach_file": "Adjuntar archivo/correo en SAP CRM",
        "monday_update_pipeline": "Actualizar pipeline de propuestas en Monday.com",
        "monday_log_activity": "Registrar actividad en bitacora Monday.com",
        "session_client_followup": "Capturar insights de sesion con cliente",
        "session_internal_alignment": "Documentar sesion interna de alineamiento",
        "session_product_learning": "Registrar aprendizaje de nuevo producto/servicio",
    }
    return descriptions.get(task, task)


# -- Verificacion de preset cargado -------------------------------------------
# Claves representativas de los dominios GBM (si al menos 3 existen, el preset esta cargado)
_GBM_DOMAIN_KEYS = {"sow", "bom", "sap_tierra", "monday", "business_rules", "catalog"}


def is_preset_loaded() -> bool:
    """
    Verifica si los dominios GBM estan presentes en domains.json.
    Retorna True si al menos 3 de las claves GBM existen en el archivo.
    """
    if not DOMAINS_FILE.exists():
        return False
    try:
        data = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        matches = _GBM_DOMAIN_KEYS.intersection(data.keys())
        return len(matches) >= 3
    except Exception:
        return False
