# -*- coding: utf-8 -*-
"""
user_prompt_submit.py -- Hook UserPromptSubmit: experiencia relevante por tarea
===============================================================================
Se dispara cuando el usuario envia un mensaje.
Su stdout se inyecta como contexto ANTES de que el CLI procese el mensaje.

FLUJO:
  1. Lee el prompt del usuario desde stdin
  2. Clasifica tipo de mensaje (instruction/informing/informational)
  3. domain_detector detecta dominios con IDF (multi-dominio si tarea mixta)
  4. Cache: si mismo tema reciente, respuesta instantanea sin re-clasificar
  5. Busca en learning_memory los patrones de ESE tema
  6. Busca en knowledge_base las recetas de ESE tema
  7. Busca en episodic_index sesiones anteriores relevantes
  8. Co-ocurrencia + Markov predictivo para contexto anticipado
  9. Intent detection + momentum tracking
  10. Inyecta solo lo relevante

Fusion de Motor 1 (on_user_message.py) + Motor 2 (user_prompt_submit.py).
Sin API keys. Sin servicios externos. Todo local.
"""

import sys
import json
import math
import re
from pathlib import Path
from datetime import datetime

# -- path setup: parent = Motor_IA root
_MOTOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MOTOR_DIR))

from config import (
    LAST_MSG_FILE, NOTIFY_FILE, CLASSIFY_CACHE, CO_OCCUR_FILE,
    MARKOV_FILE, PROMPT_HIST_FILE, INJECTION_FILE, MSG_TYPE_FILE,
    HOOK_STATE_DIR, DATA_DIR,
    CACHE_TTL_SECS, CACHE_OVERLAP_THRESHOLD,
)

CACHE_OVERLAP_TH = CACHE_OVERLAP_THRESHOLD  # alias local para compatibilidad

KB_FILE_CACHE: dict = {}  # {filepath: (mtime, data)} -- cache en proceso


# ======================================================================
#  STOP WORDS
# ======================================================================

STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "que",
    "y", "a", "por", "con", "para", "es", "se", "no", "lo", "le", "su",
    "me", "te", "si", "mi", "tu", "al", "hay", "ya", "pero", "como",
    "the", "an", "in", "of", "to", "is", "it", "for", "and", "or",
    "puedo", "quiero", "hacer", "haz", "dame", "muestra", "dime",
    "necesito", "ver", "este", "esta", "esto", "cuando", "donde",
    "algo", "mas", "muy", "bien", "ok", "eso", "asi", "cual",
}


# ======================================================================
#  CLASIFICACION CACHE (disco, TTL 2h)
# ======================================================================

def _kw_overlap(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def _read_classify_cache(keywords: list):
    try:
        if not CLASSIFY_CACHE.exists():
            return None
        c = json.loads(CLASSIFY_CACHE.read_text(encoding="utf-8"))
        age = (datetime.now() - datetime.fromisoformat(c["ts"])).total_seconds()
        if age > CACHE_TTL_SECS:
            return None
        if _kw_overlap(keywords, c.get("keywords", [])) >= CACHE_OVERLAP_TH:
            return {"domains": c["domains"], "keywords": c["keywords"]}
    except Exception:
        pass
    return None


def _write_classify_cache(domains: list, keywords: list):
    try:
        CLASSIFY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CLASSIFY_CACHE.write_text(
            json.dumps({
                "domains": domains,
                "keywords": keywords,
                "ts": datetime.now().isoformat(),
            }, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


# ======================================================================
#  EXTRACCION DE KEYWORDS
# ======================================================================

def extract_keywords(text: str) -> list:
    words = re.findall(r'\b[a-zA-Z0-9_\u00e0-\u00ff]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS][:25]


# ======================================================================
#  CLASIFICACION DE DOMINIOS CON IDF
# ======================================================================

# Hints dinamicos -- se cargan desde disco
DOMAIN_HINTS: dict = {}


def classify_domains(keywords: list) -> list:
    """
    Clasificador multi-dominio con scoring ponderado e IDF.
    1. Intenta usar core.domain_detector si existe (Motor 2 style).
    2. Fallback: inline IDF scoring contra domain_hints.json (Motor 1 style).
    Retorna hasta 3 dominios relevantes.
    """
    # Intento 1: domain_detector modular
    try:
        from core.domain_detector import detect_multi
        text = " ".join(keywords)
        domains = detect_multi(text, max_domains=3)
        if domains:
            return domains
    except (ImportError, Exception):
        pass

    # Intento 2: inline IDF scoring (Motor 1 approach)
    try:
        from core.knowledge_base import _load_all_domains
        all_domains = _load_all_domains()

        # Cargar keywords aprendidas por dominio
        hints_file = DATA_DIR / "knowledge" / "domain_hints.json"
        learned_hints = {}
        if hints_file.exists():
            try:
                learned_hints = json.loads(hints_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        else:
            try:
                hints_file.parent.mkdir(parents=True, exist_ok=True)
                hints_file.write_text("{}", encoding="utf-8")
            except Exception:
                pass

        for dname in all_domains:
            if dname not in DOMAIN_HINTS:
                if dname in learned_hints:
                    DOMAIN_HINTS[dname] = learned_hints[dname]
                else:
                    DOMAIN_HINTS[dname] = {dname.replace("_", ""): 2, dname: 3}
    except Exception:
        pass

    text = " ".join(keywords)
    scores: dict = {}

    # IDF: keywords que aparecen en pocos dominios tienen mayor peso discriminatorio
    kw_domain_count: dict = {}
    for hints in DOMAIN_HINTS.values():
        for kw in hints:
            kw_domain_count[kw] = kw_domain_count.get(kw, 0) + 1
    n_domains = max(len(DOMAIN_HINTS), 1)

    for domain, hint_weights in DOMAIN_HINTS.items():
        score = 0.0
        for kw, w in hint_weights.items():
            if kw in text:
                df = kw_domain_count.get(kw, 1)
                idf = math.log((n_domains + 1) / (df + 1)) + 1.0
                score += w * idf
        if score > 0:
            scores[domain] = score

    if not scores:
        return []

    max_score = max(scores.values())
    threshold = max(1, max_score * 0.50)

    relevant = sorted(
        [(d, s) for d, s in scores.items() if s >= threshold],
        key=lambda x: -x[1]
    )
    return [d for d, _ in relevant[:3]]


# ======================================================================
#  MEMORY RECALL DETECTION
# ======================================================================

MEMORY_RECALL_PATTERNS = [
    r"recuerdas?\s+(lo\s+)?(ultimo|ultimo|que\s+estab)",
    r"(en\s+qu[eé]|qu[eé])\s+estab[as]+\s+(haciendo|trabajando)",
    r"(qu[eé]|c[oó]mo)\s+(estab[as]+|qued[oó])\s+",
    r"\b(ultimo|ultimo)\s+(que\s+)?(hiciste|estabas|trabajamos|vimos)\b",
    r"\bqu[eé]\s+(estaba[sz]?|ten[ií]as?)\s+pendiente\b",
    r"\bsigue\s+(con|desde)\s+(lo\s+)?(anterior|ultimo|ultimo)\b",
    r"\bcontinu[aá]\s+(desde\s+)?(donde|lo)\b",
    r"\ba?\s*qu[eé]\s+nos\s+quedamos\b",
    r"\bde\s+qu[eé]\s+(estab[aá]mos|hablamos|tratamos)\b",
]


def is_memory_recall(prompt: str) -> bool:
    text = prompt.lower()
    for pat in MEMORY_RECALL_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def get_latest_session_summary() -> str:
    """Retorna la nota de la sesion episodica mas reciente del KB."""
    try:
        kb_dir = DATA_DIR / "knowledge"
        best_key = ""
        best_notes = ""
        for patterns_file in kb_dir.glob("*/patterns.json"):
            try:
                data = json.loads(patterns_file.read_text(encoding="utf-8"))
                for _, val in data.get("entries", {}).items():
                    if not isinstance(val, dict):
                        continue
                    key = val.get("key", "")
                    if "session_auto_" not in key and "session_complete" not in key:
                        continue
                    if key > best_key:
                        sol = val.get("solution", {})
                        notes = sol.get("notes", "") if isinstance(sol, dict) else ""
                        if notes.strip():
                            best_key = key
                            best_notes = notes
            except Exception:
                continue
        if best_key and best_notes:
            ts = best_key.replace("session_auto_", "").replace("_", "-", 2) if "session_auto_" in best_key else best_key
            return f"[{ts}] {best_notes[:400]}"
    except Exception:
        pass
    return ""


# ======================================================================
#  GUARDAR ULTIMO MENSAJE (para crash recovery)
# ======================================================================

def save_last_user_message(hook_input: dict):
    try:
        prompt = hook_input.get("prompt", "").strip()
        if not prompt:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        LAST_MSG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_MSG_FILE.write_text(
            f"[{ts}] session:{hook_input.get('session_id', '')}\n{prompt}\n",
            encoding="utf-8"
        )
    except Exception:
        pass


# ======================================================================
#  BUSQUEDA EN LEARNING MEMORY
# ======================================================================

def search_lm(keywords: list, domains: list) -> str:
    """Busca patrones aprendidos (errores + soluciones) para los dominios detectados."""
    try:
        from core.learning_memory import export_for_context, get_stats, _load_memory
        if get_stats().get("total_patterns", 0) == 0:
            return ""

        results = []
        for domain in domains:
            export = export_for_context(task_type=domain, limit=2)
            if export and "No hay patrones" not in export:
                results.append(f"[{domain}]\n{export}")

        if results:
            return "\n".join(results)

        # Fallback: buscar por keywords en todos los patrones
        mem = _load_memory()
        candidates = []
        for pid, p in mem["patterns"].items():
            searchable = " ".join([
                " ".join(p.get("tags", [])),
                p.get("task_type", ""),
                p.get("context_key", ""),
            ]).lower()
            if any(kw in searchable for kw in keywords[:6]):
                candidates.append(p)

        if candidates:
            candidates.sort(
                key=lambda x: x["stats"].get("success_rate", 0), reverse=True
            )
            lines = []
            for p in candidates[:4]:
                sol = p.get("solution", {})
                sr = p["stats"].get("success_rate", 0)
                lines.append(f"  [PATRON] exito {sr*100:.0f}% -- USAR ESTE APPROACH:")
                if sol.get("notes"):
                    lines.append(f"    {sol['notes'][:200]}")
                if sol.get("code_snippet"):
                    lines.append(f"    codigo: {sol['code_snippet'][:150]}")
            return "\n".join(lines)
    except Exception:
        pass
    return ""


# ======================================================================
#  BUSQUEDA EN KNOWLEDGE BASE
# ======================================================================

def search_kb(keywords: list, domains: list) -> str:
    """
    Busca recetas en los dominios detectados.
    B: "general" siempre incluido (base transversal).
    A: si hay < 2 entradas en dominios detectados, fallback a cross_search sin filtro.
    """
    try:
        from core.knowledge_base import cross_domain_search

        query = " ".join(keywords[:8])
        results = cross_domain_search(text_query=query, domains=domains or None)

        lines = []
        total_entries = 0
        for dom, entries in results.items():
            if not entries:
                continue
            total_entries += len(entries)
            lines.append(f"  [{dom}]")
            for e in entries[:2]:
                key = e.get("key", "?")
                if e.get("type") == "pattern":
                    sol = e.get("solution", {})
                    strategy = sol.get("strategy", "")
                    notes = sol.get("notes", "")[:200]
                    if strategy:
                        lines.append(f"    {key}: {strategy}")
                        if notes:
                            lines.append(f"      {notes}")
                elif e.get("type") == "fact":
                    fact = e.get("fact", {})
                    rule = fact.get("rule", "")[:200]
                    if rule:
                        lines.append(f"    APLICAR -> {key}: {rule}")
                        for ex in fact.get("examples", [])[:2]:
                            lines.append(
                                f"      ej: {ex.get('input','?')} -> {ex.get('output','?')}"
                            )

        # Fallback cross_search si hay pocos resultados en dominios detectados
        if total_entries < 2:
            fallback = cross_domain_search(text_query=query, domains=None)
            for dom, entries in fallback.items():
                if dom in (domains or []) or not entries:
                    continue
                lines.append(f"  [{dom}]")
                for e in entries[:1]:
                    key = e.get("key", "?")
                    if e.get("type") == "pattern":
                        sol = e.get("solution", {})
                        if sol.get("strategy"):
                            lines.append(f"    {key}: {sol['strategy']}")
                            if sol.get("notes"):
                                lines.append(f"      {sol['notes'][:200]}")
                    elif e.get("type") == "fact":
                        fact = e.get("fact", {})
                        if fact.get("rule"):
                            lines.append(f"    APLICAR -> {key}: {fact['rule'][:200]}")

        return "\n".join(lines)
    except Exception:
        pass
    return ""


# ======================================================================
#  CO-DOMINIO PREDICTIVO + MARKOV
# ======================================================================

def get_co_domains(domains: list) -> list:
    """
    Lee la tabla de co-ocurrencia historica y retorna el dominio que mas
    frecuentemente aparece junto con los dominios detectados.
    """
    try:
        if not CO_OCCUR_FILE.exists():
            return []
        data = json.loads(CO_OCCUR_FILE.read_text(encoding="utf-8"))
        extra = []
        for dom in domains:
            co = data.get(dom, {})
            if not co:
                continue
            top = max(co, key=lambda k: co[k])
            if top not in domains and top not in extra:
                extra.append(top)
        return extra[:1]  # max 1 co-dominio para no saturar contexto
    except Exception:
        return []


def get_markov_next(domains: list, co_domains: list) -> list:
    """
    Prediccion 2 pasos adelante con cadena de Markov ordinal.
    Dado el dominio actual, predice el SIGUIENTE dominio mas probable.
    Diferencia vs co-ocurrencia: Markov es DIRIGIDO (sow->bom, no bom->sow).
    """
    try:
        if not MARKOV_FILE.exists():
            return []
        data = json.loads(MARKOV_FILE.read_text(encoding="utf-8"))
        all_known = set(domains + co_domains)
        predictions = []
        for dom in domains:
            transitions = data.get(dom, {})
            if not transitions:
                continue
            candidates = [(k, v) for k, v in transitions.items() if k not in all_known]
            if candidates:
                next_dom = max(candidates, key=lambda x: x[1])[0]
                if next_dom not in predictions:
                    predictions.append(next_dom)
        return predictions[:1]
    except Exception:
        return []


# ======================================================================
#  BUSQUEDA EPISODICA
# ======================================================================

def search_episodic(keywords: list, limit: int = 3) -> str:
    """Busca en el indice FTS5 de sesiones anteriores."""
    try:
        from core.episodic_index import search as ep_search
        query = " ".join(keywords[:6])
        results = ep_search(query, limit=limit)
        if not results:
            return ""
        lines = []
        for r in results:
            date = r.get("date", "?")
            domain = r.get("domain", "?")
            snippet = r.get("snippet", "")[:150]
            lines.append(f"  [{date}/{domain}] {snippet}")
        return "\n".join(lines)
    except Exception:
        return ""


# ======================================================================
#  INTENT CLASSIFICATION + MOMENTUM
# ======================================================================

INTENT_PATTERNS = {
    "crear":       ["crea", "genera", "nuevo", "construye", "arma", "escribe", "redacta",
                    "make", "create", "new", "draft", "plantilla", "template"],
    "revisar":     ["revisa", "checa", "verifica", "audita", "valida",
                    "review", "check", "audit", "analiza", "inspecciona"],
    "depurar":     ["error", "falla", "no funciona", "roto", "fix", "arregla", "broken",
                    "debug", "fallo", "exception", "traceback", "problema"],
    "automatizar": ["automatiza", "script", "hook", "proceso", "pipeline",
                    "auto", "schedule", "cron", "repite"],
    "entender":    ["explica", "como", "por que", "dime", "explain",
                    "how", "describe", "detalla"],
}

INTENT_CONTEXT = {
    "crear":       "Priorizar templates y estructuras del KB.",
    "revisar":     "Priorizar checklists y patrones de validacion.",
    "depurar":     "Priorizar patrones de error y fixes probados.",
    "automatizar": "Priorizar scripts y hooks existentes.",
    "entender":    "Priorizar documentacion y ejemplos del KB.",
    "general":     "",
}


def detect_intent(prompt: str) -> str:
    """Detecta intencion principal: crear / revisar / depurar / automatizar / entender."""
    text = prompt.lower()
    scores = {
        intent: sum(1 for p in patterns if p in text)
        for intent, patterns in INTENT_PATTERNS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def update_prompt_history(prompt: str, domains: list, intent: str):
    """Historial rolling de los ultimos 5 prompts para detectar momentum."""
    try:
        PROMPT_HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "ts":      datetime.now().isoformat(),
            "domains": domains,
            "intent":  intent,
            "head":    prompt[:80],
        }, ensure_ascii=False)
        lines = []
        if PROMPT_HIST_FILE.exists():
            lines = PROMPT_HIST_FILE.read_text(encoding="utf-8").splitlines()
        lines.append(entry)
        PROMPT_HIST_FILE.write_text("\n".join(lines[-5:]), encoding="utf-8")
    except Exception:
        pass


def get_momentum(current_domains: list) -> str:
    """
    Detecta si el usuario esta en deep_work (mismo dominio repetido)
    o context_switch (cambio de dominio).
    """
    try:
        if not PROMPT_HIST_FILE.exists():
            return "neutral"
        lines = PROMPT_HIST_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) < 2:
            return "neutral"
        recent = [json.loads(l) for l in lines[-3:] if l.strip()]
        domain_matches = sum(
            1 for h in recent
            if any(d in h.get("domains", []) for d in current_domains)
        )
        return "deep_work" if domain_matches >= 2 else "context_switch"
    except Exception:
        return "neutral"


# ======================================================================
#  CLASIFICACION DE TIPO DE MENSAJE
# ======================================================================

_INSTRUCTION_VERBS = {
    "crea", "genera", "agrega", "anade", "quita", "borra", "elimina",
    "modifica", "actualiza", "cambia", "instala", "conecta", "ejecuta",
    "implementa", "arregla", "limpia", "construye", "arma", "escribe",
    "sube", "despliega", "configura", "edita", "mueve", "renombra",
    "haz", "hazlo", "aplica", "procede",
    "make", "create", "add", "remove", "delete", "update", "fix", "run",
    "build", "deploy", "install", "connect", "execute", "generate",
}

_INFORMING_PATTERNS = [
    r"\bfyi\b", r"\bsabe\s+que\b", r"\bnota\b", r"\brecuerda\s+que\b",
    r"\bte\s+(cuento|informo|digo|aviso)\b", r"\bpara\s+que\s+sepas\b",
    r"\besto\s+(es|fue|paso)\b", r"\bten\s+en\s+cuenta\b",
    r"\bcontexto\b.*:", r"\bimportante\b.*:",
]

_INFORMATIONAL_PATTERNS = [
    r"^(que|qu[eé]|cual|cu[aá]l|quien|qui[eé]n)\s+(es|son|fue|significa|hace|pasa)",
    r"^(como|c[oó]mo)\s+(funciona|se\s+usa|es\s+que|se\s+hace)",
    r"^(por\s+que|por\s+qu[eé]|cuando|d[oó]nde|cuanto)",
    r"^(explica|describe|dime|muestra|dame\s+info|que\s+es)",
    r"^(puedes\s+explicar|puedes\s+decirme|sabes\s+que)",
    r"\?$",
]


def classify_message_type(prompt: str) -> str:
    """
    Clasifica el mensaje:
      'instruction'   -- tarea a ejecutar     -> SIEMPRE grabar
      'informing'     -- usuario da contexto  -> grabar
      'informational' -- pregunta pura        -> NO grabar (salvo sin KB)
    """
    text = prompt.lower().strip()
    words = set(re.findall(r'\b\w+\b', text))

    # 1. Revision rapida: contiene verbo de accion => instruccion
    if words & _INSTRUCTION_VERBS:
        return "instruction"
    # "si procede" o similares
    if re.search(r'\b(si\s+procede|go\s+ahead|adelante|hazlo|done|listo\s+para)\b', text):
        return "instruction"

    # 2. Patron de informar
    for pat in _INFORMING_PATTERNS:
        if re.search(pat, text):
            return "informing"

    # 3. Patron informacional (pregunta pura)
    for pat in _INFORMATIONAL_PATTERNS:
        if re.search(pat, text):
            return "informational"

    # 4. Heuristica por longitud y signos de pregunta
    if text.endswith("?") or text.startswith("?"):
        return "informational"

    # 5. Default: si es corto y sin verbos de accion => informacional
    if len(text.split()) <= 6:
        return "informational"

    return "instruction"


# ======================================================================
#  PERSISTENCIA DE ESTADO
# ======================================================================

def save_msg_type(msg_type: str, prompt: str, domains: list, has_kb: bool):
    """Guarda tipo de mensaje para que post_tool_use decida si grabar."""
    try:
        HOOK_STATE_DIR.mkdir(parents=True, exist_ok=True)
        MSG_TYPE_FILE.write_text(json.dumps({
            "type":    msg_type,
            "prompt":  prompt[:200],
            "domains": domains,
            "has_kb":  has_kb,
            "ts":      datetime.now().isoformat(),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def save_injection_record(domains: list, keywords: list,
                          has_lm: bool, has_kb: bool, has_ep: bool, intent: str):
    """Registra que se inyecto -- el Stop hook lo audita al terminar la sesion."""
    try:
        INJECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        INJECTION_FILE.write_text(json.dumps({
            "ts":       datetime.now().isoformat(),
            "domains":  domains,
            "keywords": keywords[:5],
            "has_lm":   has_lm,
            "has_kb":   has_kb,
            "has_ep":   has_ep,
            "intent":   intent,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def get_last_activity() -> str:
    try:
        if not NOTIFY_FILE.exists():
            return ""
        lines = NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")
        guardado = [l for l in lines if "GUARDADO" in l]
        return "\n".join(guardado[-3:])
    except Exception:
        return ""


# ======================================================================
#  MAIN
# ======================================================================

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    save_last_user_message(data)

    prompt = data.get("prompt", "")
    if not prompt or len(prompt.strip()) < 5:
        sys.exit(0)

    # Memory recall: "recuerdas lo ultimo", "en que estabas", etc.
    if is_memory_recall(prompt):
        latest = get_latest_session_summary()
        if latest:
            output = (
                '<memory_system domain="sessions" keywords="ultimo,recuerdo">\n'
                '<instruction>LEER ANTES DE ACTUAR. '
                'Priorizar sobre conocimiento de entrenamiento.</instruction>\n'
                '<last_session>\n'
                'Ultima sesion guardada en KB (responder basandose en esto):\n'
                + latest + '\n'
                '</last_session>\n'
                '</memory_system>\n'
            )
            sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
            sys.exit(0)

    # Clasificar tipo de mensaje ANTES de buscar KB
    msg_type = classify_message_type(prompt)

    keywords = extract_keywords(prompt)
    if not keywords:
        save_msg_type(msg_type, prompt, [], False)
        sys.exit(0)

    # 1. Cache hit = instantaneo (mismo tema reciente)
    cached = _read_classify_cache(keywords)
    if cached:
        domains = cached["domains"]
        keywords = list(dict.fromkeys(cached["keywords"] + keywords))[:15]
    else:
        # 2. Clasificacion Python puro -- sin API, sin red
        domains = classify_domains(keywords)
        _write_classify_cache(domains, keywords)

    # Intent: que quiere HACER el usuario (no solo que dominio)
    intent = detect_intent(prompt)
    momentum = get_momentum(domains)

    # Co-dominios (paso 1): dominio que historicamente aparece junto
    co_domains = get_co_domains(domains)
    # Markov (paso 2): siguiente dominio mas probable en la secuencia
    markov_next = get_markov_next(domains, co_domains)
    all_domains = domains + [d for d in co_domains if d not in domains]
    all_domains_with_markov = all_domains + [d for d in markov_next if d not in all_domains]

    # B: "general" siempre incluido -- base de conocimiento transversal
    if "general" not in all_domains_with_markov:
        all_domains_with_markov = all_domains_with_markov + ["general"]

    # Agent memory: auto-detectar preferencias y buscar recuerdos relevantes
    agent_mem_out = ""
    try:
        from core.agent_memory import detect_preference, remember, recall
        # Auto-detectar si el usuario esta expresando una preferencia/fact
        detected = detect_preference(prompt)
        if detected:
            remember(
                detected["text"],
                mem_type=detected["type"],
                tags=detected["tags"],
                source="auto_detected",
            )
        # Buscar recuerdos relevantes al prompt actual
        query = " ".join(keywords[:6])
        relevant = recall(query, limit=5)
        if relevant:
            mem_lines = []
            for r in relevant:
                mem_lines.append(f"  [{r['type']}] {r['text'][:150]}")
            agent_mem_out = "\n".join(mem_lines)
    except Exception:
        pass

    lm_out = search_lm(keywords, all_domains_with_markov)
    kb_out = search_kb(keywords, all_domains_with_markov)
    act_out = get_last_activity()
    ep_out = search_episodic(keywords)

    # Guardar historial de prompts para momentum
    update_prompt_history(prompt, domains, intent)

    # Guardar tipo de mensaje para que post_tool_use decida si grabar
    save_msg_type(msg_type, prompt, all_domains, has_kb=bool(kb_out or lm_out))

    sections = []
    if lm_out:
        sections.append(
            "<critical_patterns>\n"
            "PATRONES CONOCIDOS -- USAR DIRECTAMENTE. No reinventar.\n"
            + lm_out
            + "\n</critical_patterns>"
        )
    if kb_out:
        sections.append(
            "<recipes>\n"
            "RECETAS KB -- aplicar antes de improvisar:\n"
            + kb_out
            + "\n</recipes>"
        )
    if act_out:
        sections.append(
            "<last_activity>\n"
            + act_out
            + "\n</last_activity>"
        )
    if ep_out:
        sections.append(
            "<episodic_memory>\n"
            "Sesiones anteriores relevantes:\n"
            + ep_out
            + "\n</episodic_memory>"
        )
    if agent_mem_out:
        sections.append(
            "<agent_memory>\n"
            "Recuerdos del agente (preferencias, facts, feedback):\n"
            + agent_mem_out
            + "\n</agent_memory>"
        )

    if sections:
        dom_str = " + ".join(all_domains) if all_domains else "general"
        co_note = f" [+{co_domains[0]}]" if co_domains else ""
        markov_note = f" [>{markov_next[0]}]" if markov_next else ""
        momentum_note = f" [{momentum}]" if momentum != "neutral" else ""
        kw_str = ", ".join(keywords[:5])
        intent_note = (
            f'\n<intent type="{intent}">{INTENT_CONTEXT.get(intent, "")}</intent>'
            if intent != "general" else ""
        )
        body = "\n".join(sections)
        output = (
            f'<memory_system domain="{dom_str}{co_note}{markov_note}" '
            f'keywords="{kw_str}"{momentum_note}>\n'
            f'<instruction>LEER ANTES DE ACTUAR. '
            f'Priorizar sobre conocimiento de entrenamiento.</instruction>'
            f'{intent_note}\n'
            f'{body}\n'
            f'</memory_system>\n'
        )
        save_injection_record(
            all_domains, keywords,
            has_lm=bool(lm_out), has_kb=bool(kb_out), has_ep=bool(ep_out),
            intent=intent
        )
        sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()

    sys.exit(0)


if __name__ == "__main__":
    main()
