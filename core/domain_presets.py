# -*- coding: utf-8 -*-
"""
domain_presets.py -- Perfiles de dominios predefinidos (opcionales)
===================================================================
Los dominios NO se cargan por defecto. El usuario elige un preset
durante la instalacion, o empieza desde 0 y el motor crea dominios
dinamicamente segun el uso.

Cada preset es un dict de dominios con keywords iniciales.
El usuario puede cargar multiples presets (se fusionan).
"""

PRESETS = {
    "solution_advisor_gbm": {
        "label": "Solution Advisor GBM",
        "description": "13 dominios para Solution Advisor en GBM Guatemala: SOW, BoM, SAP CRM, Monday, BPM, Outlook, etc.",
        "domains": {
            "sow": {
                "description": "SOWs: generacion desde BoM, revision, fusion, propuesta economica, estructura GBM",
                "keywords": ["sow", "statement_of_work", "alcance", "entregable", "revision", "contradiccion",
                             "fecha", "monto", "ambiguedad", "incoherencia", "fusion", "practica",
                             "renovacion", "proyecto", "bolsa", "rfp", "celula", "plantilla"],
                "tasks": ["sow_generate", "sow_review", "sow_fusion", "sow_economic"]
            },
            "bom": {
                "description": "Bills of Materials: validacion, numeros de parte, clasificacion, tipo de cambio, pricing",
                "keywords": ["bom", "bill_of_materials", "part_number", "numero_parte", "servicio", "licencia",
                             "software", "hardware", "hibrido", "tipo_cambio", "pricing", "mep",
                             "excel", "fusion", "precio", "costo"],
                "tasks": ["bom_validate", "bom_fusion", "bom_to_proposal", "bom_fx_strategy", "bom_payment_split"]
            },
            "pptx": {
                "description": "Presentaciones PowerPoint: resumen propuestas, ofrecimiento productos/servicios, decks",
                "keywords": ["pptx", "powerpoint", "presentacion", "deck", "slide", "resumen",
                             "propuesta", "producto", "servicio", "ejecutivo", "ofrecimiento"],
                "tasks": ["pptx_proposal_summary", "pptx_product_offering"]
            },
            "sap_tierra": {
                "description": "SAP CRM Web (Tierra): quotes, items, oportunidades, piezas, licencias, Playwright",
                "keywords": ["sap", "tierra", "crm", "quote", "oportunidad", "item", "pieza",
                             "licencia", "costo", "soporte", "asistencia", "asesoria", "playwright",
                             "webui", "iframe", "manual", "contrato", "estandar"],
                "tasks": ["sap_login", "sap_quote_manual", "sap_quote_contrato", "sap_quote_estandar",
                          "sap_fill_items", "sap_attach_file", "sap_navigate_frames"]
            },
            "sap_nube": {
                "description": "SAP CRM Nube: version cloud, formularios, oportunidades",
                "keywords": ["sap_nube", "crm_cloud", "nube", "cloud", "formulario", "oportunidad_nube"],
                "tasks": ["sap_nube_quote", "sap_nube_items", "sap_nube_navigation"]
            },
            "monday": {
                "description": "Monday.com: seguimiento propuestas, pipeline, costos, bitacora actividades",
                "keywords": ["monday", "pipeline", "propuesta", "etapa", "costo", "valor_venta",
                             "criticidad", "producto", "servicio", "bitacora", "actividad", "seguimiento"],
                "tasks": ["monday_update_pipeline", "monday_log_activity", "monday_import_data"]
            },
            "bpm_bau": {
                "description": "BPM BAU: procesos, formularios, pestanas, autorizacion",
                "keywords": ["bpm", "bau", "proceso", "formulario", "pestana", "autorizacion",
                             "aprobacion", "workflow", "disparar"],
                "tasks": ["bau_start_process", "bau_fill_form", "bau_approval_flow"]
            },
            "outlook": {
                "description": "Outlook: correos, adjuntos, guardar correos, attachar en SAP",
                "keywords": ["outlook", "correo", "email", "adjunto", "attachment", "enviar",
                             "guardar", "pdf", "sap"],
                "tasks": ["outlook_send", "outlook_save_as_attachment", "outlook_to_sap"]
            },
            "files": {
                "description": "Archivos multi-formato: PDF, Excel, TXT, DOCX, JPG, PPTX, conversiones, OCR",
                "keywords": ["archivo", "file", "pdf", "excel", "txt", "docx", "jpg", "pptx",
                             "conversion", "ocr", "merge", "extraccion", "texto"],
                "tasks": ["file_convert", "file_extract_text", "file_merge_pdfs"]
            },
            "sessions": {
                "description": "Sesiones y reuniones: seguimiento cliente, alineamiento interno, aprendizaje productos",
                "keywords": ["sesion", "reunion", "cliente", "upsell", "extension", "preventa",
                             "delivery", "am", "alineamiento", "producto", "aprendizaje"],
                "tasks": ["session_client_followup", "session_internal_alignment", "session_product_learning"]
            },
            "business_rules": {
                "description": "Reglas de negocio GBM: nomenclatura, tarifas, clausulas, SLAs, pricing, IVA",
                "keywords": ["regla", "negocio", "nomenclatura", "codigo", "_ps", "_rn", "tarifa",
                             "clausula", "sla", "proceso", "pricing", "iva", "convencion", "quote"],
                "tasks": []
            },
            "catalog": {
                "description": "Catalogo productos/servicios: IBM, SAP, GBM, codigos, precios, SKUs",
                "keywords": ["catalogo", "producto", "servicio", "ibm", "db2", "was", "mq", "instana",
                             "sap_licencia", "soporte", "asistencia", "asesoria", "celula", "desarrollo",
                             "codigo", "precio", "sku"],
                "tasks": []
            },
            "general": {
                "description": "Dominio general para consultas que no encajan en ningun otro dominio",
                "keywords": ["general", "otro", "consulta", "pregunta", "ayuda"],
                "tasks": []
            }
        }
    },
    "software_developer": {
        "label": "Desarrollador de Software",
        "description": "Dominios comunes para desarrollo: git, testing, CI/CD, frontend, backend, databases, devops.",
        "domains": {
            "git_vcs": {
                "description": "Control de versiones: git, branches, merges, PRs, conflicts",
                "keywords": ["git", "branch", "merge", "commit", "pull", "push", "rebase", "cherry-pick",
                             "stash", "conflict", "remote", "origin", "checkout", "diff", "log", "blame"],
                "tasks": ["git_branch_management", "git_conflict_resolution", "git_workflow"]
            },
            "testing": {
                "description": "Testing: unit, integration, e2e, mocking, coverage, TDD",
                "keywords": ["test", "unittest", "pytest", "jest", "mocha", "cypress", "selenium",
                             "mock", "stub", "fixture", "coverage", "assert", "expect", "tdd", "bdd"],
                "tasks": ["write_unit_tests", "write_e2e_tests", "fix_failing_tests"]
            },
            "frontend": {
                "description": "Frontend: React, Vue, Angular, CSS, HTML, responsive, UI/UX",
                "keywords": ["react", "vue", "angular", "svelte", "css", "html", "tailwind", "bootstrap",
                             "component", "hook", "state", "props", "render", "dom", "responsive",
                             "flexbox", "grid"],
                "tasks": ["build_component", "fix_css", "responsive_layout"]
            },
            "backend": {
                "description": "Backend: APIs, REST, GraphQL, authentication, middleware, servers",
                "keywords": ["api", "rest", "graphql", "endpoint", "middleware", "authentication",
                             "authorization", "jwt", "oauth", "cors", "route", "controller", "service",
                             "express", "fastapi", "django", "flask"],
                "tasks": ["build_api", "fix_endpoint", "add_authentication"]
            },
            "databases": {
                "description": "Bases de datos: SQL, NoSQL, migrations, queries, ORM",
                "keywords": ["sql", "mysql", "postgresql", "postgres", "mongodb", "redis", "sqlite",
                             "query", "migration", "schema", "index", "join", "orm", "prisma",
                             "sequelize", "alembic"],
                "tasks": ["write_query", "create_migration", "optimize_query"]
            },
            "devops": {
                "description": "DevOps: Docker, CI/CD, cloud, deployment, monitoring",
                "keywords": ["docker", "kubernetes", "k8s", "ci", "cd", "pipeline", "github_actions",
                             "jenkins", "aws", "azure", "gcp", "deploy", "nginx", "terraform",
                             "ansible", "monitoring", "grafana"],
                "tasks": ["setup_pipeline", "dockerize", "deploy_to_cloud"]
            }
        }
    },
    "data_science": {
        "label": "Data Science / Analytics",
        "description": "Dominios para ciencia de datos: analisis, ML, visualizacion, ETL, estadistica.",
        "domains": {
            "data_analysis": {
                "description": "Analisis de datos: pandas, numpy, limpieza, transformacion",
                "keywords": ["pandas", "numpy", "dataframe", "csv", "excel", "limpieza",
                             "transformacion", "merge", "groupby", "pivot", "filter", "aggregate",
                             "null", "missing", "outlier"],
                "tasks": ["clean_data", "transform_data", "merge_datasets"]
            },
            "machine_learning": {
                "description": "Machine Learning: modelos, entrenamiento, evaluacion, sklearn, tensorflow",
                "keywords": ["modelo", "model", "train", "predict", "sklearn", "tensorflow", "pytorch",
                             "regression", "classification", "clustering", "neural", "accuracy", "loss",
                             "epoch", "feature", "label"],
                "tasks": ["train_model", "evaluate_model", "feature_engineering"]
            },
            "visualization": {
                "description": "Visualizacion: graficos, dashboards, matplotlib, plotly, PowerBI",
                "keywords": ["grafico", "chart", "plot", "matplotlib", "plotly", "seaborn", "dashboard",
                             "powerbi", "tableau", "histogram", "scatter", "bar", "line", "heatmap"],
                "tasks": ["create_chart", "build_dashboard", "create_report"]
            },
            "etl_pipeline": {
                "description": "ETL: extraccion, transformacion, carga, pipelines de datos",
                "keywords": ["etl", "pipeline", "extract", "transform", "load", "airflow", "spark",
                             "batch", "streaming", "kafka", "warehouse", "lake", "ingestion",
                             "schedule", "cron"],
                "tasks": ["build_etl", "schedule_pipeline", "fix_data_pipeline"]
            }
        }
    },
    "business_admin": {
        "label": "Administracion de Empresas",
        "description": "Dominios para administracion: contabilidad, RRHH, ventas, logistica, legal.",
        "domains": {
            "contabilidad": {
                "description": "Contabilidad: facturas, impuestos, estados financieros, SAT, IVA",
                "keywords": ["factura", "impuesto", "iva", "sat", "contabilidad", "balance",
                             "estado_financiero", "ingreso", "egreso", "costo", "gasto", "utilidad",
                             "depreciacion", "amortizacion", "libro_diario", "mayor"],
                "tasks": ["registrar_factura", "calcular_impuestos", "generar_estado_financiero"]
            },
            "recursos_humanos": {
                "description": "RRHH: nomina, vacaciones, contratos, evaluaciones, reclutamiento",
                "keywords": ["nomina", "vacacion", "contrato", "empleado", "reclutamiento",
                             "evaluacion", "desempeno", "capacitacion", "liquidacion", "igss",
                             "bono14", "aguinaldo", "planilla"],
                "tasks": ["calcular_nomina", "gestionar_vacaciones", "evaluar_desempeno"]
            },
            "ventas": {
                "description": "Ventas: cotizaciones, clientes, pipeline, CRM, comisiones",
                "keywords": ["cotizacion", "cliente", "venta", "pipeline", "crm", "comision",
                             "descuento", "precio", "negociacion", "cierre", "prospecto", "lead",
                             "oportunidad", "propuesta"],
                "tasks": ["crear_cotizacion", "seguimiento_cliente", "cerrar_venta"]
            },
            "logistica": {
                "description": "Logistica: inventario, despacho, proveedores, compras, bodega",
                "keywords": ["inventario", "despacho", "proveedor", "compra", "bodega", "almacen",
                             "orden_compra", "recepcion", "stock", "kardex", "sku", "lote", "envio",
                             "transporte"],
                "tasks": ["gestionar_inventario", "orden_de_compra", "despachar_pedido"]
            }
        }
    }
}


def list_presets() -> list[dict]:
    """Retorna lista de presets disponibles con label y description."""
    return [
        {"id": k, "label": v["label"], "description": v["description"], "domain_count": len(v["domains"])}
        for k, v in PRESETS.items()
    ]


def get_preset(preset_id: str) -> dict | None:
    """Retorna un preset por su id, o None si no existe."""
    return PRESETS.get(preset_id)


def apply_preset(preset_id: str) -> int:
    """
    Carga un preset al domains.json usando domain_detector.learn_domain_keywords().
    Retorna el numero de dominios creados.
    """
    preset = PRESETS.get(preset_id)
    if not preset:
        return 0

    from core.domain_detector import learn_domain_keywords

    count = 0
    for domain_name, domain_data in preset["domains"].items():
        keywords = domain_data.get("keywords", [])
        if keywords:
            learn_domain_keywords(domain_name, keywords)
            count += 1
    return count


def apply_multiple_presets(preset_ids: list[str]) -> int:
    """Carga multiples presets. Los keywords se fusionan si hay dominios repetidos."""
    total = 0
    for pid in preset_ids:
        total += apply_preset(pid)
    return total
