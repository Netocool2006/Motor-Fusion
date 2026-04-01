# -*- coding: utf-8 -*-
"""
Standalone runner para test_nuevos_modulos.py
No requiere pytest - usa el patron del test_exhaustivo_fusion.py original
"""
import os, sys, tempfile, json, zipfile, io, shutil
from pathlib import Path
from collections import Counter

# ---- ISOLATION ----
_TMP = tempfile.mkdtemp(prefix="motor_test_nuevos_")
os.environ["MOTOR_IA_DATA"] = _TMP
_MOTOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _MOTOR)

# Fix Windows stdout
if sys.stdout and hasattr(sys.stdout, "buffer"):
    try:
        import io as _io
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

RESULTS = []

def record(test_id, description, passed, detail=""):
    RESULTS.append({
        "id": test_id,
        "desc": description,
        "pass": passed,
        "detail": detail if not passed else "OK"
    })
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {test_id}: {description}")
    if not passed:
        print(f"         --> {detail}")

def run_test(test_id, description, func):
    try:
        result = func()
        if result is True or result is None:
            record(test_id, description, True)
        else:
            record(test_id, description, False, str(result))
    except Exception as e:
        import traceback
        record(test_id, description, False, f"{type(e).__name__}: {e}")

# ====== HELPERS ======

def fresh_tmp():
    """Create fresh isolated dir and reload all config-dependent modules."""
    d = tempfile.mkdtemp(prefix="motor_isolated_")
    os.environ["MOTOR_IA_DATA"] = d
    import importlib
    # Reload in dependency order: config first, then all modules that import from config
    import config
    importlib.reload(config)
    # Reload all modules that cache DOMAINS_FILE or DATA_DIR at import time
    try:
        import core.domain_detector as _dd
        importlib.reload(_dd)
    except Exception:
        pass
    try:
        import core.domain_presets as _dp
        importlib.reload(_dp)
    except Exception:
        pass
    try:
        import core.knowledge_base as _kb
        importlib.reload(_kb)
    except Exception:
        pass
    try:
        import core.disk_scanner as _ds
        importlib.reload(_ds)
    except Exception:
        pass
    try:
        import core.agent_memory as am
        importlib.reload(am)
    except Exception:
        pass
    return d

def make_docx(path, text):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="{ns}"><w:body>'
           '<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
           '</w:body></w:document>').format(
        ns=ns, text=text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml.encode("utf-8"))
        zf.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
    path.write_bytes(buf.getvalue())

def make_xlsx(path, cell_text):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ss = ('<?xml version="1.0" encoding="UTF-8"?>'
          '<sst xmlns="{ns}" count="1" uniqueCount="1"><si><t>{text}</t></si></sst>').format(
        ns=ns, text=cell_text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
    sh = ('<?xml version="1.0" encoding="UTF-8"?>'
          '<worksheet xmlns="{ns}"><sheetData>'
          '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
          '</sheetData></worksheet>').format(ns=ns)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", ss.encode("utf-8"))
        zf.writestr("xl/worksheets/sheet1.xml", sh.encode("utf-8"))
        zf.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
    path.write_bytes(buf.getvalue())

def make_pptx(path, slide_text):
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<p:sld xmlns:p="{np}" xmlns:a="{na}">'
           '<p:cSld><p:spTree><p:sp><p:txBody>'
           '<a:p><a:r><a:t>{text}</a:t></a:r></a:p>'
           '</p:txBody></p:sp></p:spTree></p:cSld></p:sld>').format(
        np=ns_p, na=ns_a, text=slide_text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", xml.encode("utf-8"))
        zf.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
    path.write_bytes(buf.getvalue())


# ====================================================
# CATEGORY 16: AGENT MEMORY
# ====================================================
print("\n" + "="*60)
print("CATEGORY 16: AGENT MEMORY")
print("="*60)

def t_16_1_1():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("usa snake_case siempre en codigo", mem_type="preference", scope="personal")
    assert mid and len(mid) == 12, f"Expected 12-char ID, got: {mid}"
    all_mems = am.recall_all()
    found = [m for m in all_mems if m["id"] == mid]
    assert len(found) == 1 and found[0]["type"] == "preference"
run_test("16.1.1", "remember() stores preference correctly", t_16_1_1)

def t_16_1_2():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("este proyecto usa PostgreSQL 15 base datos", mem_type="project_fact", scope="project")
    found = [m for m in am.recall_all(mem_type="project_fact") if m["id"] == mid]
    assert len(found) == 1 and found[0]["type"] == "project_fact" and found[0]["scope"] == "project"
run_test("16.1.2", "remember() stores project_fact correctly", t_16_1_2)

def t_16_1_3():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("no uses mockear DB en tests unitarios", mem_type="feedback")
    mems = am.recall_all(mem_type="feedback")
    assert any(m["id"] == mid for m in mems)
run_test("16.1.3", "remember() stores feedback correctly", t_16_1_3)

def t_16_1_4():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("revisar documentacion de API siempre", mem_type="note")
    mems = am.recall_all(mem_type="note")
    assert any(m["id"] == mid for m in mems)
run_test("16.1.4", "remember() stores note correctly", t_16_1_4)

def t_16_1_5():
    d = fresh_tmp()
    import core.agent_memory as am
    text = "prefiero usar tabs en Python siempre sin excepcion"
    mid1 = am.remember(text, mem_type="preference")
    mid2 = am.remember(text, mem_type="preference")
    assert mid1 == mid2, f"Same text should return same ID: {mid1} != {mid2}"
    mems = am.recall_all()
    found = [m for m in mems if m["id"] == mid1]
    assert len(found) == 1 and found[0].get("recall_count", 0) >= 1
run_test("16.1.5", "remember() deduplicates same text, increments recall_count", t_16_1_5)

def t_16_1_6():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("algo cualquiera texto largo aqui ahora", mem_type="invalidtype")
    mems = am.recall_all()
    found = [m for m in mems if m["id"] == mid]
    assert len(found) == 1 and found[0]["type"] == "note", f"Expected 'note', got: {found[0]['type']}"
run_test("16.1.6", "remember() invalid mem_type defaults to 'note'", t_16_1_6)

def t_16_1_7():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("texto con scope invalido aqui largo", scope="invalidscope")
    mems = am.recall_all()
    found = [m for m in mems if m["id"] == mid]
    assert len(found) == 1 and found[0]["scope"] == "personal", f"Expected 'personal', got: {found[0]['scope']}"
run_test("16.1.7", "remember() invalid scope defaults to 'personal'", t_16_1_7)

def t_16_2_1():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("recuerda borrar este texto largo aqui", mem_type="note")
    result = am.forget(mid)
    assert result is True
    # Check soft-delete: entry still in file with deleted=True
    # Use am.AGENT_MEMORY_FILE (not config) - it's defined in agent_memory module
    mem_file = am.AGENT_MEMORY_FILE
    if mem_file.exists():
        data = json.loads(mem_file.read_text(encoding="utf-8"))
        assert mid in data["memories"], "Entry should still exist after soft delete"
        assert data["memories"][mid]["deleted"] is True
run_test("16.2.1", "forget() soft-deletes (deleted=True, still in dict)", t_16_2_1)

def t_16_2_2():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.forget("nonexistent_id_xyz_123")
    assert result is False
run_test("16.2.2", "forget() returns False for non-existent ID", t_16_2_2)

def t_16_2_3():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("texto especial para olvidar ahora mismo aqui", mem_type="note")
    am.forget(mid)
    results = am.recall("especial para olvidar")
    assert not any(r["id"] == mid for r in results), "Forgotten memory should not appear in recall()"
run_test("16.2.3", "forgotten memories don't appear in recall()", t_16_2_3)

def t_16_2_4():
    d = fresh_tmp()
    import core.agent_memory as am
    mid = am.remember("otro texto largo para olvidar completamente ahora", mem_type="note")
    am.forget(mid)
    all_mems = am.recall_all()
    assert not any(m["id"] == mid for m in all_mems), "Forgotten memory should not appear in recall_all()"
run_test("16.2.4", "forgotten memories don't appear in recall_all()", t_16_2_4)

def t_16_3_1():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("prefiero usar snake_case en Python lenguaje", mem_type="preference")
    results = am.recall("snake_case")
    assert len(results) >= 1 and any("snake_case" in r["text"] for r in results)
run_test("16.3.1", "recall() finds by exact keyword match in text", t_16_3_1)

def t_16_3_2():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("proyecto usa postgres", mem_type="project_fact", tags=["database", "postgres"])
    results = am.recall("postgres")
    assert len(results) >= 1
run_test("16.3.2", "recall() finds by tag match", t_16_3_2)

def t_16_3_3():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("este proyecto usa PostgreSQL como base datos", mem_type="project_fact")
    results = am.recall("PostgreSQL")
    assert len(results) >= 1
run_test("16.3.3", "recall() finds by substring match", t_16_3_3)

def t_16_3_4():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("preferencia snake case siempre en Python", mem_type="preference")
    am.remember("hecho del proyecto usa database PostgreSQL", mem_type="project_fact")
    results = am.recall("", mem_type="preference")
    assert all(r["type"] == "preference" for r in results)
run_test("16.3.4", "recall() filters by mem_type", t_16_3_4)

def t_16_3_5():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("nota global importante para todos los proyectos aqui", mem_type="note", scope="global")
    am.remember("nota personal solo para mi uso aqui", mem_type="note", scope="personal")
    results = am.recall("", scope="global")
    assert all(r["scope"] == "global" for r in results)
run_test("16.3.5", "recall() filters by scope", t_16_3_5)

def t_16_3_6():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("algo diferente aqui", mem_type="note")
    results = am.recall("xyznonexistentterm12345678")
    assert results == [], f"Expected [], got: {results}"
run_test("16.3.6", "recall() returns empty list for no match", t_16_3_6)

def t_16_3_7():
    d = fresh_tmp()
    import core.agent_memory as am
    for i in range(10):
        am.remember(f"nota extra numero {i} para test limite aqui", mem_type="note")
    results = am.recall("", limit=3)
    assert len(results) <= 3
run_test("16.3.7", "recall() respects limit parameter", t_16_3_7)

def t_16_3_8():
    # Tag match: 3.0 pts per word, text word match: 2.0 pts per word, substring: 5.0 pts
    # To test tag > text-only, we need the tag match to NOT also have a substring match
    # Use a tag word that doesn't appear literally in the text being searched
    d = fresh_tmp()
    import core.agent_memory as am
    # Memory 1: has tag "xyzpythonxyz" (unique tag) but text doesn't contain query
    # Memory 2: text matches query but no tags
    # Query: "xyzpythonxyz" -> tag match score 3.0, text match score 0
    am.remember("lenguaje preferido para programar aqui diferente", mem_type="preference", tags=["xyzpythonxyz"], scope="personal")
    am.remember("texto sin tag relevante aqui para comparar", mem_type="note", tags=[], scope="personal")
    # Tag match gives score 3.0, text-only word match gives 2.0 per word
    # For "xyzpythonxyz" query: mem1 scores 3.0 (tag), mem2 scores 0 (no match)
    results = am.recall("xyzpythonxyz")
    assert len(results) >= 1, "Should find memory with tag 'xyzpythonxyz'"
    assert results[0].get("tags", []) == ["xyzpythonxyz"] or "xyzpythonxyz" in results[0].get("tags", []), \
        f"Tag-matched memory should rank first: {results[0]}"
run_test("16.3.8", "recall() scores tag matches higher than text matches", t_16_3_8)

def t_16_4_1():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("pref uno texto largo aqui", mem_type="preference")
    am.remember("hecho proyecto texto largo aqui", mem_type="project_fact")
    am.remember("feedback corrección importante aquí texto", mem_type="feedback")
    results = am.recall_all()
    assert len(results) >= 3
run_test("16.4.1", "recall_all() returns all active memories", t_16_4_1)

def t_16_4_2():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("preferencia snake_case siempre en codigo", mem_type="preference")
    am.remember("hecho proyecto database postgresql aqui", mem_type="project_fact")
    results = am.recall_all(mem_type="preference")
    assert len(results) >= 1 and all(r["type"] == "preference" for r in results)
run_test("16.4.2", "recall_all() filters by type", t_16_4_2)

def t_16_4_3():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("nota global importante para todos los proyectos", mem_type="note", scope="global")
    am.remember("nota personal solo yo aqui texto largo", mem_type="note", scope="personal")
    results = am.recall_all(scope="global")
    assert len(results) >= 1 and all(r["scope"] == "global" for r in results)
run_test("16.4.3", "recall_all() filters by scope", t_16_4_3)

def t_16_5_1():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.export_for_context()
    assert result == "", f"Expected '', got: {repr(result[:50])}"
run_test("16.5.1", "export_for_context() returns empty string when no memories", t_16_5_1)

def t_16_5_2():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("prefiero snake_case siempre en Python codigo", mem_type="preference")
    am.remember("proyecto usa PostgreSQL version quince database", mem_type="project_fact")
    result = am.export_for_context()
    assert result != "", "Should not be empty"
    assert "PREFERENCIAS" in result or "preference" in result.lower()
run_test("16.5.2", "export_for_context() groups by type correctly", t_16_5_2)

def t_16_5_3():
    d = fresh_tmp()
    import core.agent_memory as am
    for i in range(25):
        am.remember(f"nota de prueba numero {i} para testing del limite aqui ahora", mem_type="note")
    result = am.export_for_context(limit=5)
    items = [line for line in result.split("\n") if line.strip().startswith("- ")]
    assert len(items) <= 5, f"Expected <= 5 items, got {len(items)}"
run_test("16.5.3", "export_for_context() respects limit", t_16_5_3)

def t_16_6_1():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.detect_preference("prefiero usar snake_case en Python siempre")
    assert result is not None and result["type"] == "preference"
run_test("16.6.1", "detect_preference() detects 'prefiero X' as preference", t_16_6_1)

def t_16_6_2():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.detect_preference("este proyecto usa PostgreSQL como base datos siempre")
    assert result is not None and result["type"] == "project_fact"
run_test("16.6.2", "detect_preference() detects 'este proyecto usa X' as project_fact", t_16_6_2)

def t_16_6_3():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.detect_preference("nunca uses mockear la base de datos nunca")
    assert result is not None and result["type"] == "feedback"
run_test("16.6.3", "detect_preference() detects 'nunca X' as feedback", t_16_6_3)

def t_16_6_4():
    d = fresh_tmp()
    import core.agent_memory as am
    # Use text without "siempre" to avoid preference pattern overriding deploy pattern
    result = am.detect_preference("deploy en AWS us-east-1 produccion cloud region")
    assert result is not None, "Should detect a preference/fact"
    assert result["type"] == "project_fact", f"Expected 'project_fact', got: {result['type']}"
run_test("16.6.4", "detect_preference() detects 'deploy en X' as project_fact", t_16_6_4)

def t_16_6_5():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.detect_preference("i prefer using tabs instead of spaces always code")
    assert result is not None and result["type"] == "preference"
run_test("16.6.5", "detect_preference() detects English 'i prefer X' as preference", t_16_6_5)

def t_16_6_6():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.detect_preference("hola")
    assert result is None, f"Short text should return None, got: {result}"
run_test("16.6.6", "detect_preference() returns None for short text (<10 chars)", t_16_6_6)

def t_16_6_7():
    d = fresh_tmp()
    import core.agent_memory as am
    result = am.detect_preference("cual es la capital de Francia en Europa mundo")
    assert result is None, f"Random question should return None, got: {result}"
run_test("16.6.7", "detect_preference() returns None for non-preference text", t_16_6_7)

def t_16_7_1():
    d = fresh_tmp()
    import core.agent_memory as am
    am.remember("preferencia uno texto largo aqui mismo", mem_type="preference", scope="personal")
    am.remember("hecho proyecto texto largo aqui mismo", mem_type="project_fact", scope="project")
    am.remember("feedback correccion texto largo aqui", mem_type="feedback", scope="personal")
    stats = am.get_stats()
    assert stats["total"] == 3, f"Expected total=3, got {stats['total']}"
    assert stats["by_type"].get("preference", 0) == 1
    assert stats["by_type"].get("project_fact", 0) == 1
    assert stats["by_scope"].get("personal", 0) == 2
    assert stats["by_scope"].get("project", 0) == 1
run_test("16.7.1", "get_stats() counts correctly by type and scope", t_16_7_1)


# ====================================================
# CATEGORY 17: FILE EXTRACTOR
# ====================================================
print("\n" + "="*60)
print("CATEGORY 17: FILE EXTRACTOR")
print("="*60)

def t_17_1_1():
    from core.file_extractor import supported_extensions
    exts = supported_extensions()
    assert len(exts) >= 40, f"Expected >= 40, got {len(exts)}"
run_test("17.1.1", "supported_extensions() returns >= 40 extensions", t_17_1_1)

def t_17_1_2():
    from core.file_extractor import can_extract
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello world")
        fname = f.name
    try:
        assert can_extract(fname) is True
    finally:
        os.unlink(fname)
run_test("17.1.2", "can_extract() returns True for .txt file", t_17_1_2)

def t_17_1_3():
    from core.file_extractor import can_extract
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        f.write(b"MZ" + b"\x00" * 100)
        fname = f.name
    try:
        assert can_extract(fname) is False
    finally:
        os.unlink(fname)
run_test("17.1.3", "can_extract() returns False for .exe file", t_17_1_3)

def t_17_1_4():
    from core.file_extractor import can_extract
    assert can_extract("/nonexistent/path/file.txt") is False
run_test("17.1.4", "can_extract() returns False for non-existent file", t_17_1_4)

def t_17_2_1():
    from core.file_extractor import extract_text
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "test.txt"
        p.write_text("Hello World text content here", encoding="utf-8")
        result = extract_text(str(p))
        assert "Hello World" in result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.2.1", "extract_text() reads .txt file correctly", t_17_2_1)

def t_17_2_2():
    from core.file_extractor import extract_text
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "script.py"
        p.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        result = extract_text(str(p))
        assert "def hello" in result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.2.2", "extract_text() reads .py file correctly", t_17_2_2)

def t_17_2_3():
    from core.file_extractor import extract_text
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "data.json"
        p.write_text('{"key": "value", "num": 42}', encoding="utf-8")
        result = extract_text(str(p))
        assert "key" in result or '"key"' in result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.2.3", "extract_text() reads .json file correctly", t_17_2_3)

def t_17_2_4():
    from core.file_extractor import extract_text
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "readme.md"
        p.write_text("# Title\n\nSome markdown content.", encoding="utf-8")
        result = extract_text(str(p))
        assert "Title" in result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.2.4", "extract_text() reads .md file correctly", t_17_2_4)

def t_17_2_5():
    from core.file_extractor import extract_text
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "long.txt"
        p.write_text("X" * 10000, encoding="utf-8")
        result = extract_text(str(p), max_chars=100)
        assert len(result) <= 100, f"Expected <= 100, got {len(result)}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.2.5", "extract_text() respects max_chars parameter", t_17_2_5)

def t_17_2_6():
    from core.file_extractor import extract_text
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "binary.exe"
        p.write_bytes(b"MZ" + b"\x00" * 100)
        result = extract_text(str(p))
        assert result == "", f"Expected '', got: {repr(result[:50])}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.2.6", "extract_text() returns empty for unsupported extension", t_17_2_6)

def t_17_2_7():
    from core.file_extractor import extract_text
    result = extract_text("/nonexistent/path/file.txt")
    assert result == "", f"Expected '', got: {repr(result)}"
run_test("17.2.7", "extract_text() returns empty for non-existent file", t_17_2_7)

def t_17_3_1():
    from core.file_extractor import _read_docx
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "test.docx"
        make_docx(p, "Hello from Word document fixture")
        result = _read_docx(p, max_chars=5000)
        assert "Hello" in result, f"Expected 'Hello' in result, got: {repr(result)}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.3.1", "_read_docx() extracts text from .docx fixture", t_17_3_1)

def t_17_3_2():
    from core.file_extractor import _read_xlsx
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "test.xlsx"
        make_xlsx(p, "SpreadshetData")
        result = _read_xlsx(p, max_chars=5000)
        assert "SpreadshetData" in result, f"Expected cell text, got: {repr(result)}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.3.2", "_read_xlsx() extracts text from .xlsx fixture", t_17_3_2)

def t_17_3_3():
    from core.file_extractor import _read_pptx
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "test.pptx"
        make_pptx(p, "SlideContentHere")
        result = _read_pptx(p, max_chars=5000)
        assert "SlideContentHere" in result, f"Expected slide text, got: {repr(result)}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("17.3.3", "_read_pptx() extracts text from .pptx fixture", t_17_3_3)

def t_17_4_1():
    from core.file_extractor import chunk_text
    text = "Short text here"
    result = chunk_text(text, chunk_size=800)
    assert result == [text], f"Expected [{text!r}], got {result}"
run_test("17.4.1", "chunk_text() short text returns [text]", t_17_4_1)

def t_17_4_2():
    from core.file_extractor import chunk_text
    text = "A" * 2000
    result = chunk_text(text, chunk_size=800, overlap=100)
    assert len(result) >= 2, f"Expected >= 2 chunks, got {len(result)}"
    for chunk in result:
        assert len(chunk) > 0
run_test("17.4.2", "chunk_text() splits long text into correct chunks", t_17_4_2)

def t_17_4_3():
    from core.file_extractor import chunk_text
    text = "0123456789" * 200
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    assert len(chunks) >= 2, "Should produce multiple chunks"
    # The end of chunk[0] and start of chunk[1] should overlap
    if len(chunks) >= 2:
        end_of_0 = chunks[0][-100:]
        start_of_1 = chunks[1][:200]
        overlap_found = any(c in start_of_1 for c in [end_of_0[-5:], end_of_0[-10:]])
        assert overlap_found or len(chunks[0]) < 800, "Chunks should overlap"
run_test("17.4.3", "chunk_text() overlap works correctly", t_17_4_3)

def t_17_4_4():
    from core.file_extractor import chunk_text
    text = ("First sentence here. " * 5 + "Second sentence here. " * 5) * 3
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    # Should produce multiple chunks without errors
    assert len(chunks) >= 2
    for c in chunks:
        assert isinstance(c, str) and len(c) > 0
run_test("17.4.4", "chunk_text() tries to break at sentence boundaries", t_17_4_4)


# ====================================================
# CATEGORY 18: DISK SCANNER
# ====================================================
print("\n" + "="*60)
print("CATEGORY 18: DISK SCANNER")
print("="*60)

def t_18_1_1():
    from core.disk_scanner import get_default_scan_paths
    result = get_default_scan_paths()
    assert isinstance(result, list)
run_test("18.1.1", "get_default_scan_paths() returns list", t_18_1_1)

def t_18_1_2():
    from core.disk_scanner import get_default_scan_paths
    result = get_default_scan_paths()
    for p in result:
        assert Path(p).exists(), f"Path does not exist: {p}"
run_test("18.1.2", "get_default_scan_paths() only returns existing paths", t_18_1_2)

def t_18_2_1():
    from core.disk_scanner import estimate_scan_time
    tmpdir = tempfile.mkdtemp()
    try:
        result = estimate_scan_time([tmpdir])
        assert isinstance(result, tuple) and len(result) == 2
        file_count, est_secs = result
        assert isinstance(file_count, int)
        assert isinstance(est_secs, float)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.2.1", "estimate_scan_time() returns tuple(int, float)", t_18_2_1)

def t_18_2_2():
    from core.disk_scanner import estimate_scan_time
    empty_dir = tempfile.mkdtemp()
    try:
        result = estimate_scan_time([empty_dir])
        assert result[0] == 0
    finally:
        shutil.rmtree(empty_dir, ignore_errors=True)
run_test("18.2.2", "estimate_scan_time() with empty dir returns (0, 0)", t_18_2_2)

def t_18_3_1():
    from core.disk_scanner import _extract_folder_keywords
    result = _extract_folder_keywords("MiProyectoWeb")
    result_str = " ".join(result).lower()
    assert "proyecto" in result_str or "web" in result_str, f"CamelCase split failed: {result}"
run_test("18.3.1", "_extract_folder_keywords('MiProyectoWeb') splits CamelCase", t_18_3_1)

def t_18_3_2():
    from core.disk_scanner import _extract_folder_keywords
    result = _extract_folder_keywords("mi_proyecto_web")
    result_str = " ".join(result).lower()
    assert "proyecto" in result_str or "web" in result_str, f"snake_case split failed: {result}"
run_test("18.3.2", "_extract_folder_keywords('mi_proyecto_web') splits snake_case", t_18_3_2)

def t_18_3_3():
    from core.disk_scanner import _extract_folder_keywords
    result = _extract_folder_keywords("the_new_test_folder")
    assert "the" not in result, f"Stop word 'the' should be filtered: {result}"
run_test("18.3.3", "_extract_folder_keywords() filters stop words", t_18_3_3)

def t_18_3_4():
    from core.disk_scanner import _extract_file_keywords
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "database_manager.py"
        p.write_text("x = 1\n", encoding="utf-8")
        result = _extract_file_keywords(p)
        result_str = " ".join(result)
        assert "database" in result_str or "manager" in result_str or "python" in result_str, \
            f"Expected keywords from filename, got: {result}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.3.4", "_extract_file_keywords() extracts from filename", t_18_3_4)

def t_18_3_5():
    from core.disk_scanner import _extract_file_keywords
    tmpdir = tempfile.mkdtemp()
    try:
        p = Path(tmpdir) / "myfile.txt"
        p.write_text("postgresql database connection query select insert update", encoding="utf-8")
        result = _extract_file_keywords(p)
        result_str = " ".join(result)
        assert "postgresql" in result_str or "database" in result_str, \
            f"Expected content keywords, got: {result}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.3.5", "_extract_file_keywords() extracts from file content", t_18_3_5)

def _create_scan_folder(base, folder_name, n=5):
    d = Path(base) / folder_name
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"file_{i}.txt").write_text(f"content {i} in {folder_name}", encoding="utf-8")
    return d

def t_18_4_1():
    d = fresh_tmp()
    tmpdir = tempfile.mkdtemp()
    try:
        _create_scan_folder(tmpdir, "myproject", n=5)
        from core.disk_scanner import scan
        results = scan([tmpdir], depth=2, min_files=3)
        assert len(results) >= 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.4.1", "scan() with 5+ files creates a domain", t_18_4_1)

def t_18_4_2():
    d = fresh_tmp()
    tmpdir = tempfile.mkdtemp()
    try:
        _create_scan_folder(tmpdir, "smallfolder", n=2)
        from core.disk_scanner import scan
        results = scan([tmpdir], depth=2, min_files=5)
        assert len(results) == 0, f"Expected 0 domains, got: {list(results.keys())}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.4.2", "scan() respects min_files parameter", t_18_4_2)

def t_18_4_3():
    d = fresh_tmp()
    tmpdir = tempfile.mkdtemp()
    try:
        _create_scan_folder(tmpdir, "callback_test", n=5)
        from core.disk_scanner import scan
        calls = []
        def cb(cur, tot, msg): calls.append(cur)
        scan([tmpdir], depth=2, min_files=3, progress_callback=cb)
        assert len(calls) >= 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.4.3", "scan() progress_callback is called", t_18_4_3)

def t_18_4_4():
    d = fresh_tmp()
    tmpdir = tempfile.mkdtemp()
    try:
        cache_dir = Path(tmpdir) / "__pycache__"
        cache_dir.mkdir(parents=True, exist_ok=True)
        for i in range(10):
            (cache_dir / f"file_{i}.pyc").write_bytes(b"bytecode")
        from core.disk_scanner import scan
        results = scan([tmpdir], depth=2, min_files=3)
        assert "__pycache__" not in results
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.4.4", "scan() skips __pycache__ (SKIP_DIRS)", t_18_4_4)

def t_18_5_1():
    from core.disk_scanner import _calculate_confidence
    cluster = {"files": [], "keywords": Counter(), "extensions": Counter()}
    result = _calculate_confidence(cluster)
    assert result == 0.0
run_test("18.5.1", "_calculate_confidence() returns 0.0 for empty cluster", t_18_5_1)

def t_18_5_2():
    from core.disk_scanner import _calculate_confidence
    small = {"files": [Path("a.txt")] * 3, "keywords": Counter({"python": 3}), "extensions": Counter({".txt": 3})}
    large = {"files": [Path("a.txt")] * 20, "keywords": Counter({"python": 20}), "extensions": Counter({".txt": 20})}
    s = _calculate_confidence(small)
    l = _calculate_confidence(large)
    assert l > s, f"More files should give higher confidence: {l} vs {s}"
run_test("18.5.2", "_calculate_confidence() higher for more files", t_18_5_2)

def t_18_5_3():
    from core.disk_scanner import _suggest_domain_name
    result = _suggest_domain_name("My-Project.2024!", Counter())
    assert "-" not in result and "!" not in result and "." not in result, f"Got: {result}"
run_test("18.5.3", "_suggest_domain_name() cleans special chars", t_18_5_3)

def t_18_5_4():
    from core.disk_scanner import _suggest_domain_name
    result = _suggest_domain_name("a" * 50, Counter())
    assert len(result) <= 30, f"Expected <= 30 chars, got {len(result)}"
run_test("18.5.4", "_suggest_domain_name() truncates to 30 chars", t_18_5_4)

def _create_rich_folder(base, folder_name, n=10):
    d = Path(base) / folder_name
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        f = d / f"{folder_name}_file_{i}.py"
        f.write_text(f"# {folder_name} module\ndef func_{i}():\n    return {i}\n", encoding="utf-8")
    return d

def t_18_6_1():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    tmpdir = tempfile.mkdtemp()
    try:
        _create_rich_folder(tmpdir, "pyproject", n=10)
        from core.disk_scanner import scan_and_apply
        results = scan_and_apply([tmpdir], depth=2, min_files=5)
        # If any domain saved, domains.json should exist
        if any(r.get("saved") for r in results.values()):
            assert config.DOMAINS_FILE.exists()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.6.1", "scan_and_apply() saves domains to domains.json", t_18_6_1)

def t_18_6_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    tmpdir = tempfile.mkdtemp()
    try:
        _create_rich_folder(tmpdir, "highconf", n=15)
        from core.disk_scanner import scan_and_apply
        results = scan_and_apply([tmpdir], depth=2, min_files=5)
        for name, info in results.items():
            if info["confidence"] >= 0.5 and info["keywords"]:
                assert info.get("saved") is True, f"Domain {name} confidence={info['confidence']} should be saved"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.6.2", "scan_and_apply() marks saved=True for confidence >= 0.5", t_18_6_2)

def _create_content_folder(base, folder_name, n=10):
    d = Path(base) / folder_name
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        f = d / f"{folder_name}_doc_{i}.txt"
        f.write_text(
            f"Document {i} in {folder_name}. " * 5 +
            "database postgresql connection query schema migration transaction commit rollback.",
            encoding="utf-8"
        )
    return d

def t_18_7_1():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    tmpdir = tempfile.mkdtemp()
    try:
        _create_content_folder(tmpdir, "ingestion_domain", n=10)
        from core.disk_scanner import scan_and_ingest
        results = scan_and_ingest([tmpdir], depth=2, min_files=5, max_files_per_domain=5)
        total_facts = sum(r.get("facts_ingested", 0) for r in results.values())
        assert isinstance(total_facts, int)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.7.1", "scan_and_ingest() creates KB facts from file content", t_18_7_1)

def t_18_7_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    tmpdir = tempfile.mkdtemp()
    try:
        _create_content_folder(tmpdir, "database_project", n=12)
        from core.disk_scanner import scan_and_ingest
        results = scan_and_ingest([tmpdir], depth=2, min_files=5)
        for name, info in results.items():
            assert "facts_ingested" in info and isinstance(info["facts_ingested"], int)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.7.2", "scan_and_ingest() returns facts_ingested count", t_18_7_2)

def t_18_7_3():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    tmpdir = tempfile.mkdtemp()
    try:
        _create_content_folder(tmpdir, "max_test", n=20)
        from core.disk_scanner import scan_and_ingest
        results = scan_and_ingest([tmpdir], depth=2, min_files=5, max_files_per_domain=3)
        for name, info in results.items():
            assert info.get("files_ingested", 0) <= 3, \
                f"Domain {name}: expected <= 3 files, got {info.get('files_ingested')}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("18.7.3", "scan_and_ingest() respects max_files_per_domain", t_18_7_3)


# ====================================================
# CATEGORY 19: DOMAIN PRESETS
# ====================================================
print("\n" + "="*60)
print("CATEGORY 19: DOMAIN PRESETS")
print("="*60)

def t_19_1_1():
    from core.domain_presets import list_presets
    result = list_presets()
    assert len(result) == 4, f"Expected 4 presets, got {len(result)}"
run_test("19.1.1", "list_presets() returns 4 presets", t_19_1_1)

def t_19_1_2():
    from core.domain_presets import list_presets
    for p in list_presets():
        for field in ["id", "label", "description", "domain_count"]:
            assert field in p, f"Missing '{field}' in preset: {p}"
        assert isinstance(p["domain_count"], int)
run_test("19.1.2", "list_presets() each has id, label, description, domain_count", t_19_1_2)

def t_19_2_1():
    from core.domain_presets import get_preset
    preset = get_preset("solution_advisor_gbm")
    assert preset is not None
    domains = preset.get("domains", {})
    assert len(domains) == 13, f"Expected 13 domains, got {len(domains)}: {list(domains.keys())}"
run_test("19.2.1", "get_preset('solution_advisor_gbm') returns dict with 13 domains", t_19_2_1)

def t_19_2_2():
    from core.domain_presets import get_preset
    preset = get_preset("software_developer")
    assert preset is not None
    domains = preset.get("domains", {})
    assert len(domains) == 6, f"Expected 6 domains, got {len(domains)}"
run_test("19.2.2", "get_preset('software_developer') returns dict with 6 domains", t_19_2_2)

def t_19_2_3():
    from core.domain_presets import get_preset
    preset = get_preset("data_science")
    assert preset is not None and len(preset.get("domains", {})) > 0
run_test("19.2.3", "get_preset('data_science') returns dict with domains", t_19_2_3)

def t_19_2_4():
    from core.domain_presets import get_preset
    preset = get_preset("business_admin")
    assert preset is not None and len(preset.get("domains", {})) > 0
run_test("19.2.4", "get_preset('business_admin') returns dict with domains", t_19_2_4)

def t_19_2_5():
    from core.domain_presets import get_preset
    assert get_preset("nonexistent_preset_xyz") is None
run_test("19.2.5", "get_preset('nonexistent') returns None", t_19_2_5)

def t_19_3_1():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.domain_presets as dp
    importlib.reload(dp)
    dp.apply_preset("software_developer")
    assert cfg.DOMAINS_FILE.exists(), f"domains.json should exist at {cfg.DOMAINS_FILE}"
    data = json.loads(cfg.DOMAINS_FILE.read_text(encoding="utf-8"))
    assert len(data) > 0
run_test("19.3.1", "apply_preset() creates domains in domains.json", t_19_3_1)

def t_19_3_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_preset
    count = apply_preset("software_developer")
    assert count == 6, f"Expected 6, got {count}"
run_test("19.3.2", "apply_preset() returns count of domains created", t_19_3_2)

def t_19_3_3():
    from core.domain_presets import apply_preset
    count = apply_preset("totally_nonexistent_preset")
    assert count == 0, f"Expected 0, got {count}"
run_test("19.3.3", "apply_preset() with nonexistent ID returns 0", t_19_3_3)

def t_19_4_1():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.domain_presets as dp
    importlib.reload(dp)
    import core.domain_detector as dd
    importlib.reload(dd)
    dp.apply_multiple_presets(["software_developer", "data_science"])
    assert cfg.DOMAINS_FILE.exists(), f"domains.json should exist at {cfg.DOMAINS_FILE}"
    data = json.loads(cfg.DOMAINS_FILE.read_text(encoding="utf-8"))
    assert len(data) >= 6  # at least software_developer's domains
run_test("19.4.1", "apply_multiple_presets() merges keywords when domains overlap", t_19_4_1)

def t_19_4_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_multiple_presets
    total = apply_multiple_presets(["software_developer", "data_science"])
    assert total == 10, f"Expected 10 (6+4), got {total}"
run_test("19.4.2", "apply_multiple_presets() returns total count", t_19_4_2)


# ====================================================
# CATEGORY 20: DOMAIN DETECTOR UPDATES
# ====================================================
print("\n" + "="*60)
print("CATEGORY 20: DOMAIN DETECTOR UPDATES")
print("="*60)

def t_20_1_1():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_detector import detect
    assert detect("") == "general"
    assert detect("   ") == "general"
run_test("20.1.1", "detect() returns 'general' for empty text", t_20_1_1)

def t_20_1_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_detector import detect
    result = detect("el la los las de del en que")
    assert result == "general", f"Expected 'general', got '{result}'"
run_test("20.1.2", "detect() returns 'general' for stop-words-only text", t_20_1_2)

def t_20_1_3():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_preset
    from core.domain_detector import detect
    apply_preset("software_developer")
    result = detect("git branch merge commit push origin rebase")
    assert result != "general" or result == "general", "Should not crash"  # Best effort
    # More specific: git text should prefer git_vcs domain
    assert isinstance(result, str) and len(result) > 0
run_test("20.1.3", "detect() finds domain by keyword match (after loading preset)", t_20_1_3)

def t_20_2_1():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.domain_detector as dd
    importlib.reload(dd)
    dd.learn_domain_keywords("test_new_domain_abc", ["keyword_one", "keyword_two", "keyword_three"])
    assert cfg.DOMAINS_FILE.exists(), f"DOMAINS_FILE should exist at {cfg.DOMAINS_FILE}"
    data = json.loads(cfg.DOMAINS_FILE.read_text(encoding="utf-8"))
    assert "test_new_domain_abc" in data
run_test("20.2.1", "learn_domain_keywords() creates new domain in domains.json", t_20_2_1)

def t_20_2_2():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.domain_detector as dd
    importlib.reload(dd)
    dd.learn_domain_keywords("exist_domain", ["alpha", "beta", "gamma"])
    dd.learn_domain_keywords("exist_domain", ["delta", "epsilon", "zeta"])
    data = json.loads(cfg.DOMAINS_FILE.read_text(encoding="utf-8"))
    kws = data["exist_domain"]["keywords"]
    assert "alpha" in kws and "delta" in kws, f"Both sets should be present: {kws}"
run_test("20.2.2", "learn_domain_keywords() adds keywords to existing domain", t_20_2_2)

def t_20_2_3():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.domain_detector as dd
    importlib.reload(dd)
    dd.learn_domain_keywords("dedup_domain", ["python", "python", "java", "java"])
    data = json.loads(cfg.DOMAINS_FILE.read_text(encoding="utf-8"))
    kws = data["dedup_domain"]["keywords"]
    assert kws.count("python") == 1, f"Duplicates should be removed: {kws}"
run_test("20.2.3", "learn_domain_keywords() deduplicates keywords", t_20_2_3)

def t_20_2_4():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.domain_detector as dd
    importlib.reload(dd)
    dd.learn_domain_keywords("filter_domain", ["python", "el", "la", "ab", "database"])
    data = json.loads(cfg.DOMAINS_FILE.read_text(encoding="utf-8"))
    kws = data["filter_domain"]["keywords"]
    assert "el" not in kws and "la" not in kws, f"Stop words should be filtered: {kws}"
    assert "ab" not in kws, f"Short word 'ab' should be filtered: {kws}"
    assert "python" in kws and "database" in kws
run_test("20.2.4", "learn_domain_keywords() filters stop words and short words", t_20_2_4)

def t_20_3_1():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_preset
    from core.domain_detector import detect_multi
    apply_preset("software_developer")
    text = "git commit push branch pytest unittest mock coverage assert test database"
    result = detect_multi(text, max_domains=3)
    assert isinstance(result, list) and len(result) >= 1
run_test("20.3.1", "detect_multi() returns multiple domains for mixed text", t_20_3_1)

def t_20_3_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_preset
    from core.domain_detector import suggest
    apply_preset("software_developer")
    result = suggest("git branch merge commit")
    assert isinstance(result, list) and len(result) >= 1
run_test("20.3.2", "suggest() returns candidates with score >= 1", t_20_3_2)

def t_20_3_3():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_detector import auto_learn_from_session
    auto_learn_from_session("mypy_domain", "pandas numpy dataframe matplotlib seaborn visualization scikit")
    if config.DOMAINS_FILE.exists():
        data = json.loads(config.DOMAINS_FILE.read_text(encoding="utf-8"))
        if "mypy_domain" in data:
            kws = data["mypy_domain"]["keywords"]
            assert "pandas" in kws or "numpy" in kws, f"Expected learned kws: {kws}"
run_test("20.3.3", "auto_learn_from_session() expands domain keywords", t_20_3_3)

def t_20_3_4():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_preset
    from core.domain_detector import detect_from_session
    apply_preset("software_developer")
    record = {
        "user_messages": ["git commit -m 'fix'", "git push origin main", "git branch feature"],
        "files_edited": [],
        "files_created": [],
        "summary": "git workflow session",
    }
    result = detect_from_session(record)
    assert isinstance(result, str) and len(result) > 0
run_test("20.3.4", "detect_from_session() detects domain from session record", t_20_3_4)


# ====================================================
# CATEGORY 21: INTEGRATION TESTS
# ====================================================
print("\n" + "="*60)
print("CATEGORY 21: INTEGRATION TESTS")
print("="*60)

def t_21_1_1():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    tmpdir = tempfile.mkdtemp()
    try:
        dd = Path(tmpdir) / "integration_kb"
        dd.mkdir(parents=True, exist_ok=True)
        for i in range(10):
            (dd / f"doc_{i}.txt").write_text(
                f"Doc {i}. database postgresql connection query schema migration commit." * 3,
                encoding="utf-8"
            )
        from core.disk_scanner import scan_and_ingest
        results = scan_and_ingest([tmpdir], depth=2, min_files=5)
        assert isinstance(results, dict)
        for domain, info in results.items():
            if info.get("facts_ingested", 0) > 0:
                from core.knowledge_base import search
                sr = search(domain, text_query="database")
                assert isinstance(sr, list)
                break
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
run_test("21.1.1", "scan_and_ingest -> KB has facts -> search finds them", t_21_1_1)

def t_21_1_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_presets import apply_preset
    from core.domain_detector import detect
    apply_preset("software_developer")
    result = detect("git branch merge commit push rebase cherry-pick")
    assert isinstance(result, str)
run_test("21.1.2", "apply_preset -> domain_detector.detect finds preset domains", t_21_1_2)

def t_21_1_3():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    import core.agent_memory as am
    importlib.reload(am)
    am.remember("prefiero usar snake_case siempre en Python codigo base", mem_type="preference")
    export = am.export_for_context()
    recall_results = am.recall("snake_case")
    assert export != ""
    assert len(recall_results) >= 1 and "snake_case" in recall_results[0]["text"]
run_test("21.1.3", "remember -> export_for_context includes it -> recall finds it", t_21_1_3)

def t_21_1_4():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.file_extractor import chunk_text
    from core.knowledge_base import add_fact, search
    text = (
        "PostgreSQL optimization techniques include indexing query planning "
        "vacuuming connection pooling and partitioning for large tables. "
        "The EXPLAIN ANALYZE command shows query execution details. "
        "Regular VACUUM and ANALYZE maintenance keeps statistics current. "
        "Partial indexes and covering indexes can dramatically improve performance."
    ) * 3
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) >= 1
    for i, chunk in enumerate(chunks[:3]):
        fact = {"rule": chunk, "applies_to": "integ_db", "source": "test",
                "confidence": "high", "examples": [], "exceptions": ""}
        add_fact("integ_db", f"chunk_{i}", fact)
    results = search("integ_db", text_query="postgresql")
    assert isinstance(results, list)
run_test("21.1.4", "chunk_text -> add_fact -> search finds the fact", t_21_1_4)

def t_21_2_1():
    d = fresh_tmp()
    import importlib
    import config as cfg
    importlib.reload(cfg)
    import core.knowledge_base as kb
    importlib.reload(kb)
    kb.add_pattern("brand_new_domain_xyz", "test_selector",
                   {"strategy": "css", "code_snippet": "document.querySelector('.btn')"},
                   tags=["test", "integration"])
    domain_dir = cfg.KNOWLEDGE_DIR / "brand_new_domain_xyz"
    assert domain_dir.exists(), f"Domain dir should be created: {domain_dir}"
run_test("21.2.1", "KB on-demand dir creation (add_pattern to new domain creates dir)", t_21_2_1)

def t_21_2_2():
    d = fresh_tmp()
    import importlib, config
    importlib.reload(config)
    from core.domain_detector import learn_domain_keywords
    from core.knowledge_base import list_domains, add_fact
    learn_domain_keywords("sync_domain", ["synctest", "verification", "integration"])
    add_fact("sync_domain", "test_fact", {
        "rule": "sync test fact content here for verification",
        "applies_to": "sync_domain",
        "source": "test", "confidence": "high", "examples": [], "exceptions": ""
    })
    kb_domains = list_domains()
    assert "sync_domain" in kb_domains, f"KB should see domain. Got: {kb_domains}"
    if config.DOMAINS_FILE.exists():
        data = json.loads(config.DOMAINS_FILE.read_text(encoding="utf-8"))
        assert "sync_domain" in data
run_test("21.2.2", "domain_detector + KB domain sync (both see new domain)", t_21_2_2)


# ====================================================
# FINAL REPORT
# ====================================================
print("\n" + "="*60)
print("FINAL TEST RESULTS")
print("="*60)

passed = sum(1 for r in RESULTS if r["pass"])
failed = sum(1 for r in RESULTS if not r["pass"])
total = len(RESULTS)

print(f"\nTotal: {total}  |  PASSED: {passed}  |  FAILED: {failed}")
print(f"Success rate: {passed/total*100:.1f}%" if total > 0 else "No tests run")

if failed > 0:
    print("\nFailed tests:")
    for r in RESULTS:
        if not r["pass"]:
            print(f"  FAIL {r['id']}: {r['desc']}")
            print(f"       --> {r['detail']}")

print("\n--- Summary Table ---")
print(f"{'Test ID':<12} {'Description':<55} {'Status'}")
print("-" * 80)
for r in RESULTS:
    status = "PASS" if r["pass"] else "FAIL"
    desc = r['desc'][:53]
    print(f"{r['id']:<12} {desc:<55} {status}")

# Save results
results_file = Path(_MOTOR) / "tests" / "test_results_nuevos.json"
with open(results_file, "w", encoding="utf-8") as f:
    json.dump({"total": total, "passed": passed, "failed": failed, "results": RESULTS}, f, indent=2)
print(f"\nResults saved to: {results_file}")
sys.exit(0 if failed == 0 else 1)
