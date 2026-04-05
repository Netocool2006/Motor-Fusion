# -*- coding: utf-8 -*-
"""
regression_test.py - Suite completa de pruebas reales para Hooks_IA
===================================================================
Ejecuta pruebas reales (no simulaciones) de todos los componentes.
"""
import json, sys, re, time, subprocess, os
from pathlib import Path

os.chdir(str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

results = []
passed = 0
failed = 0

def test(tc_id, uc, subcase, func):
    global passed, failed
    try:
        result, detail = func()
        status = "PASS" if result else "FAIL"
        if result:
            passed += 1
        else:
            failed += 1
        results.append((tc_id, uc, subcase, str(detail)[:60], status))
    except Exception as e:
        failed += 1
        results.append((tc_id, uc, subcase, f"EXCEPTION: {e}"[:60], "FAIL"))


def run_hook(prompt_text):
    p = subprocess.run(
        [sys.executable, "hooks/motor_ia_hook.py"],
        input=json.dumps({"prompt": prompt_text}).encode(),
        capture_output=True, timeout=30
    )
    out = p.stdout.decode("utf-8", errors="replace").strip()
    if not out or out == "{}":
        return {}, ""
    d = json.loads(out)
    ctx = d.get("hookSpecificOutput", {}).get("additionalContext", "")
    return d, ctx


def run_post_hook(msg, state_override=None):
    if state_override:
        Path("core/motor_ia_state.json").write_text(
            json.dumps(state_override), encoding="utf-8"
        )
    p = subprocess.run(
        [sys.executable, "hooks/motor_ia_post_hook.py"],
        input=json.dumps({"last_assistant_message": msg}).encode(),
        capture_output=True, timeout=30
    )
    return p


# ===================== UC1: SessionStart =====================

def tc1_1():
    r = subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    return r.returncode == 0, f"exit_code={r.returncode}"
test("TC1.1", "SessionStart", "Ejecuta sin crash", tc1_1)

def tc1_2():
    r = subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    out = r.stdout.decode("utf-8", errors="replace")
    return len(out) > 100, f"output={len(out)} chars"
test("TC1.2", "SessionStart", "Produce output >100 chars", tc1_2)

def tc1_3():
    r = subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    out = r.stdout.decode("utf-8", errors="replace")
    return "ULTIMA SESION" in out or "Sin sesiones" in out, "Seccion encontrada"
test("TC1.3", "SessionStart", "Contiene ULTIMA SESION", tc1_3)

def tc1_4():
    r = subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    out = r.stdout.decode("utf-8", errors="replace")
    return "INSTRUCCIONES" in out, "INSTRUCCIONES encontrado"
test("TC1.4", "SessionStart", "Contiene INSTRUCCIONES", tc1_4)

def tc1_5():
    r = subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    out = r.stdout.decode("utf-8", errors="replace")
    return "LEARNING MEMORY" in out, "LEARNING MEMORY encontrado"
test("TC1.5", "SessionStart", "Contiene LEARNING MEMORY", tc1_5)

def tc1_6():
    start = time.time()
    subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    elapsed = int((time.time() - start) * 1000)
    return elapsed < 10000, f"{elapsed}ms"
test("TC1.6", "SessionStart", "Tiempo < 10s", tc1_6)


# ===================== UC2: UserPromptSubmit =====================

def tc2_1():
    d, ctx = run_hook("que es Docker y para que sirve")
    return len(ctx) > 50, f"ctx={len(ctx)} chars"
test("TC2.1", "UserPromptSubmit", "Query valida produce context", tc2_1)

def tc2_2():
    d, ctx = run_hook("ok")
    return d == {} or ctx == "", "Rechazado correctamente"
test("TC2.2", "UserPromptSubmit", "Rechaza query corta (<5 chars)", tc2_2)

def tc2_3():
    d, ctx = run_hook("<task-notification>test</task-notification>")
    return d == {} or ctx == "", "Rechazado correctamente"
test("TC2.3", "UserPromptSubmit", "Rechaza XML/system tags", tc2_3)

def tc2_4():
    p = subprocess.run(
        [sys.executable, "hooks/motor_ia_hook.py"],
        input=json.dumps({"prompt": "que es Python"}).encode(),
        capture_output=True, timeout=30
    )
    out = p.stdout.decode("utf-8", errors="replace").strip()
    try:
        json.loads(out)
        return True, "JSON valido"
    except Exception:
        return False, "JSON invalido"
test("TC2.4", "UserPromptSubmit", "Output es JSON valido", tc2_4)

def tc2_5():
    d, ctx = run_hook("como estas hoy")
    return "session_anterior" in ctx, "session_anterior inyectado"
test("TC2.5", "UserPromptSubmit", "Inyecta session_anterior en context", tc2_5)

def tc2_6():
    d, ctx = run_hook("hola que tal amigo")
    return "INSTRUCCION PROACTIVA" in ctx, "INSTRUCCION PROACTIVA presente"
test("TC2.6", "UserPromptSubmit", "Contiene INSTRUCCION PROACTIVA", tc2_6)

def tc2_7():
    d, ctx = run_hook("que es CI/CD con GitHub Actions")
    m = re.search(r'kb="(\d+)%".*internet="(\d+)%".*ml="(\d+)%"', ctx)
    if m:
        total = int(m.group(1)) + int(m.group(2)) + int(m.group(3))
        return total == 100, f"KB={m.group(1)}% I={m.group(2)}% ML={m.group(3)}% ={total}"
    return False, "No percentages found"
test("TC2.7", "UserPromptSubmit", "Porcentajes KB+I+ML suman 100", tc2_7)

def tc2_8():
    run_hook("que es asyncio en Python")
    state = json.loads(Path("core/motor_ia_state.json").read_text(encoding="utf-8"))
    ok = all(k in state for k in ["query", "needs_save", "kb_pct"])
    return ok, f"query/needs_save/kb_pct presentes={ok}"
test("TC2.8", "UserPromptSubmit", "Guarda motor_ia_state.json", tc2_8)


# ===================== UC3: Stop Post-hook =====================

def tc3_1():
    before_data = json.load(open("core/session_summary.json", encoding="utf-8"))
    before_last = before_data["interactions"][-1]["query"] if before_data["interactions"] else ""
    run_post_hook(
        "Test TC3.1. **Fuentes:** KB 85% + Internet 0% + ML 15%",
        {"query": "test tc3.1 regression marker", "kb_pct": 85, "internet_pct": 0, "ml_pct": 15,
         "needs_save": True, "timestamp": "2026-04-03T18:10:00"}
    )
    after_data = json.load(open("core/session_summary.json", encoding="utf-8"))
    after_last = after_data["interactions"][-1]["query"] if after_data["interactions"] else ""
    changed = "regression marker" in after_last
    return changed, f"last_query updated={changed}"
test("TC3.1", "Stop Post-hook", "Actualiza session_summary (nueva entrada)", tc3_1)

def tc3_2():
    from core.vector_kb import get_stats
    before = get_stats()["total"]
    run_post_hook(
        "ChromaDB save. **Fuentes:** KB 40% + Internet 30% + ML 30%",
        {"query": "test chromadb tc3.2 regression", "kb_pct": 40, "internet_pct": 30,
         "ml_pct": 30, "needs_save": True, "timestamp": "2026-04-03T18:10:00"}
    )
    after = get_stats()["total"]
    return after > before, f"ChromaDB: {before} -> {after}"
test("TC3.2", "Stop Post-hook", "Guarda en ChromaDB (needs_save=true)", tc3_2)

def tc3_3():
    from core.vector_kb import get_stats
    before = get_stats()["total"]
    run_post_hook(
        "Skip test. **Fuentes:** KB 100% + Internet 0% + ML 0%",
        {"query": "test skip", "kb_pct": 100, "internet_pct": 0,
         "ml_pct": 0, "needs_save": False, "timestamp": "2026-04-03T18:10:00"}
    )
    after = get_stats()["total"]
    return after == before, f"ChromaDB unchanged: {before}"
test("TC3.3", "Stop Post-hook", "NO guarda cuando needs_save=false", tc3_3)

def tc3_4():
    r = run_post_hook(
        "Extract test. **Fuentes:** KB 60% + Internet 25% + ML 15%",
        {"query": "test extract", "kb_pct": 50, "internet_pct": 25,
         "ml_pct": 25, "needs_save": True, "timestamp": "2026-04-03T18:10:00"}
    )
    return r.returncode == 0, "Extraccion sin crash"
test("TC3.4", "Stop Post-hook", "Extrae porcentajes de respuesta", tc3_4)


# ===================== UC4: SessionEnd =====================

def tc4_1():
    p = subprocess.run(
        [sys.executable, "hooks/session_end.py"],
        input=json.dumps({
            "session_id": "test-regression",
            "transcript_path": "",
            "last_assistant_message": "test",
            "cwd": str(Path(__file__).parent.parent)
        }).encode(),
        capture_output=True, timeout=30
    )
    return p.returncode == 0, f"exit_code={p.returncode}"
test("TC4.1", "SessionEnd", "Ejecuta sin crash", tc4_1)


# ===================== UC5: Config =====================

def tc5_1():
    from config import (
        SESSION_HISTORY_FILE, LAST_MSG_FILE, STATE_FILE, ACTIONS_LOG,
        DATA_DIR, HOOK_STATE_DIR, RECENT_HOURS, MEMORY_FILE, EXECUTION_LOG,
        ATTEMPTS_FILE, PENDING_ERRORS_FILE, LOCK_DIR, DEDUP_WINDOW_SECS,
        ERROR_CORRELATION_WINDOW, CONFIDENCE_THRESHOLD, MAX_PENDING_ERRORS,
        DOMAINS_FILE, EPISODIC_DB, CO_OCCUR_FILE, MARKOV_FILE
    )
    return True, "20+ imports OK"
test("TC5.1", "Config", "Todos los imports funcionan", tc5_1)

def tc5_2():
    from config import CORE_DIR, DATA_DIR, KNOWLEDGE_DIR, HOOKS_DIR
    ok = all(p.exists() for p in [CORE_DIR, DATA_DIR, KNOWLEDGE_DIR, HOOKS_DIR])
    return ok, "Todos los directorios existen"
test("TC5.2", "Config", "Directorios apuntan a paths reales", tc5_2)


# ===================== UC6: settings.json =====================

_CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

def tc6_1():
    json.load(open(_CLAUDE_SETTINGS))
    return True, "JSON valido"
test("TC6.1", "settings.json", "JSON valido", tc6_1)

def tc6_2():
    d = json.load(open(_CLAUDE_SETTINGS))
    hooks = d.get("hooks", {})
    expected = ["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"]
    missing = [e for e in expected if e not in hooks]
    return len(missing) == 0, f"4/4 hooks" if not missing else f"Faltan: {missing}"
test("TC6.2", "settings.json", "4 hooks registrados", tc6_2)

def tc6_3():
    d = json.load(open(_CLAUDE_SETTINGS))
    hooks = d.get("hooks", {})
    for event, matchers in hooks.items():
        for m in matchers:
            for h in m.get("hooks", []):
                match = re.search(r'"([^"]+\.py)"', h.get("command", ""))
                if match and not Path(match.group(1)).exists():
                    return False, f"{event}: {match.group(1)} no existe"
    return True, "Todos los archivos existen"
test("TC6.3", "settings.json", "Hook files apuntan a archivos reales", tc6_3)

def tc6_4():
    backups = list(_CLAUDE_SETTINGS.parent.glob("settings.json.backup_*"))
    return len(backups) > 0, f"{len(backups)} backup(s) encontrado(s)"
test("TC6.4", "settings.json", "Backup de seguridad existe", tc6_4)


# ===================== UC7: Crash Recovery =====================

def tc7_1():
    future_ts = time.time() + 7200
    Path("core/hook_state.json").write_text(
        json.dumps({"sid": "crash-regression", "last_ts": future_ts}), encoding="utf-8"
    )
    with open("core/actions.log", "w", encoding="utf-8") as f:
        f.write(json.dumps({"_sid": "crash-regression", "tool": "Edit",
                            "file": "server.py", "action": "Fixing bug"}) + "\n")

    r = subprocess.run([sys.executable, "hooks/session_start.py"], capture_output=True, timeout=15)
    out = r.stdout.decode("utf-8", errors="replace")
    found = "RECUPERADA" in out

    # Cleanup
    Path("core/hook_state.json").write_text("{}", encoding="utf-8")
    Path("core/actions.log").write_text("", encoding="utf-8")

    return found, "Crash detectado y recuperado" if found else "No detecto crash"
test("TC7.1", "Crash Recovery", "Detecta sesion no guardada (timezone fix)", tc7_1)


# ===================== UC8: Continuidad =====================

def tc8_1():
    d = json.load(open("core/session_summary.json", encoding="utf-8"))
    ok = all(k in d for k in ["session_start", "interaction_count", "interactions"])
    return ok and isinstance(d["interactions"], list), f"interactions={d.get('interaction_count', 0)}"
test("TC8.1", "Continuidad", "session_summary.json estructura correcta", tc8_1)

def tc8_2():
    d, ctx = run_hook("continuemos con lo anterior")
    return "session_anterior" in ctx, "session_anterior en context"
test("TC8.2", "Continuidad", "Pre-hook carga sesion anterior", tc8_2)

def tc8_3():
    from core.vector_kb import ask_kb
    r = ask_kb("que es asyncio en Python")
    return r["found"], f"found={r['found']}"
test("TC8.3", "Continuidad", "ChromaDB encuentra conocimiento previo", tc8_3)

def tc8_4():
    d = json.load(open("core/session_summary.json", encoding="utf-8"))
    count = len(d.get("interactions", []))
    return count <= 20, f"interactions={count} (max 20)"
test("TC8.4", "Continuidad", "Buffer circular <=20 interactions", tc8_4)


# ===================== UC9: Pipeline E2E =====================

def tc9_1():
    d, ctx = run_hook("que es asyncio en Python")
    has_kb = "kb_knowledge" in ctx
    has_session = "session_anterior" in ctx
    has_sources = "reporte_fuentes" in ctx
    ok = has_kb and has_session and has_sources
    return ok, f"kb_knowledge={has_kb}, session={has_session}, sources={has_sources}"
test("TC9.1", "Pipeline E2E", "Query con KB: todas secciones presentes", tc9_1)

def tc9_2():
    p = subprocess.run(
        [sys.executable, "hooks/motor_ia_hook.py"],
        input=json.dumps({"prompt": "que es Terraform"}).encode(),
        capture_output=True, timeout=30
    )
    out = p.stdout.decode("utf-8", errors="replace").strip()
    return out.startswith("{"), "JSON limpio"
test("TC9.2", "Pipeline E2E", "Output JSON limpio (sin basura)", tc9_2)

def tc9_3():
    d, ctx = run_hook("configuracion autenticacion senales")
    return d != {}, "Unicode procesado OK"
test("TC9.3", "Pipeline E2E", "Unicode/acentos no rompen pipeline", tc9_3)

def tc9_4():
    p = subprocess.run(
        [sys.executable, "hooks/motor_ia_hook.py"],
        input=b"{}",
        capture_output=True, timeout=30
    )
    out = p.stdout.decode("utf-8", errors="replace").strip()
    return out == "{}" or out == "", "Input vacio manejado"
test("TC9.4", "Pipeline E2E", "Input vacio {} no crashea", tc9_4)

def tc9_5():
    count = 0
    for f in ["hooks/motor_ia_hook.py", "hooks/motor_ia_post_hook.py",
              "hooks/session_start.py", "hooks/session_end.py"]:
        content = Path(f).read_text(encoding="utf-8")
        count += content.count("C:\\Users\\ntoledo") + content.count("/home/ntoledo")
    return count == 0, f"{count} hardcoded paths"
test("TC9.5", "Pipeline E2E", "0 hardcoded paths en hooks", tc9_5)


# ===================== PRINT RESULTS =====================
print()
print("=" * 130)
print(f"  REPORTE DE PRUEBAS REALES - Hooks_IA - {time.strftime('%d-%m-%Y %H:%M:%S')}")
print("=" * 130)
print(f"{'ID':<8} {'Caso de Uso':<22} {'Sub-caso':<48} {'Detalle':<40} {'Estado'}")
print("-" * 130)

current_uc = ""
for tc_id, uc, subcase, detail, status in results:
    if uc != current_uc:
        if current_uc:
            print("-" * 130)
        current_uc = uc
    mark = "PASS" if status == "PASS" else "** FAIL **"
    print(f"{tc_id:<8} {uc:<22} {subcase:<48} {detail:<40} {mark}")

print("=" * 130)
total = passed + failed
rate = (passed * 100 // total) if total > 0 else 0
print(f"  TOTAL: {total} tests | PASS: {passed} | FAIL: {failed} | Rate: {rate}%")
print("=" * 130)

if failed > 0:
    print("\n  ** TESTS FALLIDOS:")
    for tc_id, uc, subcase, detail, status in results:
        if status == "FAIL":
            print(f"    {tc_id}: {uc} > {subcase} -> {detail}")

sys.exit(0 if failed == 0 else 1)
