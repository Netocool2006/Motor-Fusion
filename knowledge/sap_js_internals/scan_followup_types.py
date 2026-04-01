"""
scan_followup_types.py — Clicks each Follow-Up type (16-27), scans the resulting form, cancels, repeats.

Cycle per type:
  1. Click type in popup → popup closes, form opens in main window
  2. Wait for form to load
  3. Scan all fields/spans/buttons/dropdowns
  4. Save playbook JSON
  5. Click Cancel/Back to return to opportunity
  6. Reopen Follow-Up popup
  7. Navigate to page 2
  8. Repeat next type

Usage: python scan_followup_types.py [start_row] [end_row]
  Default: 16 27
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
import websocket

CDP_PORT = 9222
OUTPUT_DIR = Path(__file__).parent / "playbooks"
OUTPUT_DIR.mkdir(exist_ok=True)

# Types to scan (row 16-27 from Follow-Up popup page 2)
TYPES = {
    16: "Quote_Proyecto",
    17: "Cont_Quot_Man_Horas",
    18: "Cont_Quot_Manual",
    19: "Cont_Quot_VQ_Annual",
    20: "Cont_Quot_VQ_Mon",
    21: "Contr_Quot_Autom",
    22: "Contr_Quot_Cons_Auto",
    23: "Contr_Quot_Cons_Manu",
    24: "Contract_Pack_Quot",
    25: "Quotation_Standard",
    26: "Best_Pr_Task",
    27: "Internal_Task",
}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def get_tabs():
    resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json')
    return json.loads(resp.read())

class CDPSession:
    def __init__(self, ws_url, timeout=30):
        self.ws = websocket.create_connection(ws_url, timeout=timeout)
        self.msg_id = 0
        self.events = []

    def send(self, method, params=None):
        self.msg_id += 1
        mid = self.msg_id
        msg = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                self.ws.settimeout(5)
                raw = self.ws.recv()
                data = json.loads(raw)
                if data.get("id") == mid:
                    if "error" in data:
                        return {"__error": data["error"]}
                    return data.get("result", {})
                else:
                    self.events.append(data)
            except websocket.WebSocketTimeoutException:
                continue
        return {"__error": "timeout"}

    def evaluate(self, expression, context_id=None):
        params = {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
            "timeout": 15000
        }
        if context_id:
            params["contextId"] = context_id
        result = self.send("Runtime.evaluate", params)
        if "__error" in result:
            return None
        if result.get("exceptionDetails"):
            return None
        # CDP returns {result: {type, value}} — extract value
        inner = result.get("result", {})
        if isinstance(inner, dict):
            return inner.get("value")
        return inner

    def close(self):
        try:
            self.ws.close()
        except:
            pass

def get_frame_contexts(cdp):
    """Get frame tree and execution contexts."""
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    time.sleep(1.5)

    tree = cdp.send("Page.getFrameTree")
    frames = {}
    def walk(node, depth=0):
        f = node.get("frame", {})
        fid = f.get("id", "")
        frames[fid] = {"name": f.get("name", ""), "url": f.get("url", ""), "depth": depth}
        for child in node.get("childFrames", []):
            walk(child, depth + 1)
    if "frameTree" in tree:
        walk(tree["frameTree"])

    contexts = {}
    for ev in cdp.events:
        if ev.get("method") == "Runtime.executionContextCreated":
            ctx = ev["params"].get("context", {})
            aux = ctx.get("auxData", {})
            fid = aux.get("frameId", "")
            if fid and aux.get("isDefault", True):
                contexts[fid] = ctx.get("id")

    return frames, contexts

def find_context(frames, contexts, name_contains):
    """Find execution context for a frame by name substring."""
    for fid, finfo in frames.items():
        if name_contains in finfo.get("name", ""):
            if fid in contexts:
                return contexts[fid]
    return None

SCAN_JS = """(() => {
    const result = {fields: [], spans: [], buttons: [], tables: [], dropdowns: [], checkboxes: []};

    // Fields (inputs, textareas, selects)
    document.querySelectorAll('input[type="text"], input:not([type]), textarea, select').forEach(el => {
        if (el.offsetParent === null && el.type !== 'hidden') return;
        const id = el.id || '';
        const suffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
        if (!suffix || suffix.startsWith('htmlb') || suffix.includes('_isExpanded') ||
            suffix.includes('_iscollapsed') || suffix === 'SavedSearches') return;

        let label = '';
        try {
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                label = td.previousElementSibling.textContent.trim()
                    .replace(/^[\\*\\s]+/, '').replace(/[:\\s]+$/, '');
                if (label.length > 50) label = '';
            }
        } catch(e) {}

        const entry = {
            stable_suffix: suffix,
            selector: '[id$="' + suffix + '"]',
            label: label,
            value: (el.value || '').substring(0, 60),
            type: el.tagName === 'SELECT' ? 'dropdown' : el.tagName === 'TEXTAREA' ? 'textarea' : 'input',
            editable: !el.readOnly && !el.disabled,
            visible: el.offsetParent !== null,
            id_sample: id.substring(0, 80)
        };

        if (el.tagName === 'SELECT') {
            entry.options = [];
            el.querySelectorAll('option').forEach(opt => {
                entry.options.push({value: opt.value, text: opt.textContent.trim()});
            });
            result.dropdowns.push(entry);
        }
        result.fields.push(entry);
    });

    // Checkboxes
    document.querySelectorAll('input[type="checkbox"]').forEach(el => {
        const id = el.id || '';
        const suffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
        if (!suffix) return;
        let label = '';
        try {
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                label = td.previousElementSibling.textContent.trim()
                    .replace(/^[\\*\\s]+/, '').replace(/[:\\s]+$/, '');
                if (label.length > 50) label = '';
            }
        } catch(e) {}
        result.checkboxes.push({stable_suffix: suffix, label: label, checked: el.checked});
    });

    // Read-only spans
    document.querySelectorAll('span[id], a[id]').forEach(el => {
        const id = el.id || '';
        const suffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
        if (!suffix || suffix.startsWith('htmlb') || suffix.includes('Expanded')) return;
        const text = (el.textContent || '').trim();
        if (!text || text.length > 100 || el.offsetParent === null) return;
        let label = '';
        try {
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                label = td.previousElementSibling.textContent.trim()
                    .replace(/^[\\*\\s]+/, '').replace(/[:\\s]+$/, '');
                if (label.length > 50) label = '';
            }
        } catch(e) {}
        result.spans.push({stable_suffix: suffix, label: label, value: text.substring(0, 60)});
    });

    // Buttons
    document.querySelectorAll('a[onclick], button, input[type="button"], input[type="submit"]').forEach(el => {
        const text = (el.textContent || el.value || '').trim();
        if (!text || text.length > 50 || text.length < 1) return;
        const id = el.id || '';
        const suffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
        result.buttons.push({text: text, stable_suffix: suffix, id_sample: id.substring(0, 80)});
    });

    // Tables
    document.querySelectorAll('table').forEach(tbl => {
        const headerRow = tbl.querySelector('tr');
        if (!headerRow) return;
        const headers = [];
        headerRow.querySelectorAll('th, td').forEach(cell => {
            const text = (cell.textContent || '').trim();
            if (text && text.length < 40) headers.push(text);
        });
        if (headers.length >= 2 && headers.length <= 20) {
            let title = '';
            try {
                let prev = tbl.parentElement;
                for (let i = 0; i < 5 && prev; i++) {
                    const hd = prev.querySelector('.th-tp-hd, legend, h3, h4');
                    if (hd) { title = hd.textContent.trim(); break; }
                    prev = prev.parentElement;
                }
            } catch(e) {}
            result.tables.push({title: title.substring(0, 40), columns: headers});
        }
    });

    // Tabs/navigation links (SAP assignment blocks)
    const tabs = [];
    document.querySelectorAll('[id*="TabAnchor"], [id*="tabstrip"] a, .th-tl-tp a').forEach(el => {
        const text = (el.textContent || '').trim();
        const id = el.id || '';
        const suffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
        if (text && text.length < 40) tabs.push({text: text, stable_suffix: suffix});
    });
    if (tabs.length > 0) result.tabs = tabs;

    // Deduplicate
    const seen_s = new Set();
    result.spans = result.spans.filter(s => {
        if (seen_s.has(s.stable_suffix)) return false;
        seen_s.add(s.stable_suffix); return true;
    });
    const seen_b = new Set();
    result.buttons = result.buttons.filter(b => {
        if (seen_b.has(b.text)) return false;
        seen_b.add(b.text); return true;
    });

    return result;
})()"""

# JS to click a Follow-Up type by row number
def js_click_type(row):
    return f"""(() => {{
        const el = document.querySelector('[id$="proctype_table[{row}].proc_type_descr_20"]');
        if (!el) return 'NOT_FOUND';
        el.click();
        return 'CLICKED_' + el.textContent.trim();
    }})()"""

# JS to navigate to page 2 in the popup table
JS_GO_PAGE2 = """(() => {
    const pg2 = document.querySelector('[id$="Table_pag_pg-2"]');
    if (pg2) { pg2.click(); return 'PAGE2_CLICKED'; }
    const fwd = document.querySelector('[id$="Table_pag_fwd"]');
    if (fwd) { fwd.click(); return 'FWD_CLICKED'; }
    // Check if already on page 2 (row 16 visible)
    const r16 = document.querySelector('[id$="proctype_table[16].proc_type_descr_20"]');
    if (r16) return 'ALREADY_PAGE2';
    return 'NO_PAGINATION';
})()"""

# JS to find and click "Create Follow-Up" button in opportunity
JS_CLICK_CREATE_FOLLOWUP = """(() => {
    // Look for the Create Follow-Up button
    const btns = document.querySelectorAll('button, a[onclick], input[type="button"]');
    for (const btn of btns) {
        const text = (btn.textContent || btn.value || '').trim();
        if (text.includes('Follow-Up') || text.includes('FollowUp') || text.includes('follow-up')) {
            btn.click();
            return 'CLICKED: ' + text;
        }
    }
    // Try by ID pattern
    const fu = document.querySelector('[id$="V97_but2"], [id$="CreateFollowUp"], [id*="FollowUp"]');
    if (fu) { fu.click(); return 'CLICKED_BY_ID: ' + fu.id; }
    return 'NOT_FOUND';
})()"""

# JS to click Cancel/Back to return from a form
JS_CANCEL_FORM = """(() => {
    // Try Cancel button first
    const cancel = document.querySelector('[id$="thCancelSIP"], button[title="Cancel"]');
    if (cancel) { cancel.click(); return 'CANCEL_CLICKED'; }
    // Try Back button
    const back = document.querySelector('[id$="Back"], [title*="Back"]');
    if (back) { back.click(); return 'BACK_CLICKED'; }
    // Try any cancel-like button
    const btns = document.querySelectorAll('button, a[onclick]');
    for (const btn of btns) {
        const text = (btn.textContent || '').trim().toLowerCase();
        if (text === 'cancel' || text === 'back' || text === 'close') {
            btn.click();
            return 'CLICKED: ' + text;
        }
    }
    return 'NO_CANCEL_FOUND';
})()"""


def find_popup_tab(tabs):
    """Find the Follow-Up popup tab that has page 2 content (rows 16-27)."""
    for t in tabs:
        if t.get("type") != "page":
            continue
        if "popup" not in t.get("url", "").lower():
            continue
        ws = t.get("webSocketDebuggerUrl")
        if not ws:
            continue
        try:
            cdp = CDPSession(ws, timeout=15)
            frames, contexts = get_frame_contexts(cdp)
            ctx = find_context(frames, contexts, "WorkAreaFrame1popup")
            if not ctx:
                # Try main frame
                for fid, finfo in frames.items():
                    if finfo["depth"] == 0 and fid in contexts:
                        ctx = contexts[fid]
                        break
            if ctx:
                # Check if row 16 is visible (page 2)
                val = cdp.evaluate(
                    'document.querySelector(\'[id$="proctype_table[16].proc_type_descr_20"]\') ? "PAGE2" : "NOT_PAGE2"',
                    context_id=ctx)
                log(f"  Popup {t['id'][:12]}: {val}")
                if val == "PAGE2":
                    cdp.close()
                    return t, ws
            cdp.close()
        except Exception as e:
            log(f"  Error checking popup: {e}")
    return None, None


def find_main_sap_tab(tabs, opp_id=None):
    """Find the main SAP opportunity tab."""
    for t in tabs:
        if t.get("type") != "page":
            continue
        title = t.get("title", "")
        url = t.get("url", "")
        if "chrome" in url:
            continue
        if "popup" in url.lower():
            continue
        if opp_id and opp_id not in title:
            continue
        if "SAP" in title or "Opport" in title or "Opp " in title:
            return t
    return None


def scan_main_window(main_tab):
    """Connect to main SAP tab and scan WorkAreaFrame1."""
    ws = main_tab.get("webSocketDebuggerUrl")
    if not ws:
        log("  ERROR: No websocket for main tab")
        return None

    cdp = CDPSession(ws, timeout=25)
    frames, contexts = get_frame_contexts(cdp)

    # Find WorkAreaFrame1 context
    ctx = find_context(frames, contexts, "WorkAreaFrame1")
    if not ctx:
        log("  WARNING: No WorkAreaFrame1, trying all frames")
        # Try deepest frame
        max_depth = -1
        for fid, finfo in frames.items():
            if fid in contexts and finfo["depth"] > max_depth and "popup" not in finfo["name"]:
                max_depth = finfo["depth"]
                ctx = contexts[fid]

    if not ctx:
        log("  ERROR: No execution context found")
        cdp.close()
        return None

    # Wait for content to stabilize
    time.sleep(2)

    data = cdp.evaluate(SCAN_JS, context_id=ctx)
    cdp.close()
    return data


def cancel_and_return(main_tab):
    """Cancel the current form and go back to opportunity."""
    ws = main_tab.get("webSocketDebuggerUrl")
    cdp = CDPSession(ws, timeout=20)
    frames, contexts = get_frame_contexts(cdp)
    ctx = find_context(frames, contexts, "WorkAreaFrame1")
    if not ctx:
        for fid, finfo in frames.items():
            if fid in contexts and finfo["depth"] > 0 and "popup" not in finfo["name"]:
                ctx = contexts[fid]

    if ctx:
        result = cdp.evaluate(JS_CANCEL_FORM, context_id=ctx)
        log(f"  Cancel: {result}")
    cdp.close()
    time.sleep(3)  # Wait for SAP roundtrip


def reopen_followup(main_tab):
    """Click Create Follow-Up in the opportunity to reopen the popup."""
    ws = main_tab.get("webSocketDebuggerUrl")
    cdp = CDPSession(ws, timeout=20)
    frames, contexts = get_frame_contexts(cdp)
    ctx = find_context(frames, contexts, "WorkAreaFrame1")
    if ctx:
        result = cdp.evaluate(JS_CLICK_CREATE_FOLLOWUP, context_id=ctx)
        log(f"  Reopen Follow-Up: {result}")
    cdp.close()
    time.sleep(4)  # Wait for popup to open


def navigate_popup_page2():
    """Find the new popup and navigate to page 2."""
    tabs = get_tabs()
    for t in tabs:
        if t.get("type") != "page" or "popup" not in t.get("url", "").lower():
            continue
        ws = t.get("webSocketDebuggerUrl")
        if not ws:
            continue
        try:
            cdp = CDPSession(ws, timeout=15)
            frames, contexts = get_frame_contexts(cdp)
            ctx = find_context(frames, contexts, "WorkAreaFrame1popup")
            if ctx:
                result = cdp.evaluate(JS_GO_PAGE2, context_id=ctx)
                log(f"  Page 2: {result}")
                cdp.close()
                time.sleep(2)
                return True
            cdp.close()
        except Exception as e:
            log(f"  Popup nav error: {e}")
    return False


def click_type_in_popup(row):
    """Find popup that has the given row, then click it."""
    tabs = get_tabs()
    for t in tabs:
        if t.get("type") != "page" or "popup" not in t.get("url", "").lower():
            continue
        ws = t.get("webSocketDebuggerUrl")
        if not ws:
            continue
        try:
            cdp = CDPSession(ws, timeout=15)
            frames, contexts = get_frame_contexts(cdp)
            ctx = find_context(frames, contexts, "WorkAreaFrame1popup")
            if ctx:
                # First check if this popup has the row we want
                check_js = f'document.querySelector("[id*=\\"proctype_table[{row}].proc_type_descr\\"]") ? "FOUND" : "NOPE"'
                found = cdp.evaluate(check_js, context_id=ctx)
                if found != "FOUND":
                    log(f"  Popup {t['id'][:12]}: row {row} not here, skipping")
                    cdp.close()
                    continue
                # Row found, click it
                result = cdp.evaluate(js_click_type(row), context_id=ctx)
                log(f"  Click row {row}: {result}")
                cdp.close()
                time.sleep(5)  # Wait for SAP to open the form
                return result and "CLICKED" in str(result)
            cdp.close()
        except Exception as e:
            log(f"  Click error: {e}")
    return False


def main():
    start_row = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    end_row = int(sys.argv[2]) if len(sys.argv) > 2 else 27

    log(f"=== Follow-Up Type Scanner (rows {start_row}-{end_row}) ===")

    tabs = get_tabs()
    popup_tab, popup_ws = find_popup_tab(tabs)

    if not popup_tab:
        log("ERROR: No popup with page 2 found. Make sure Follow-Up popup is open on page 2.")
        log("Trying to find any popup...")
        # Maybe it's on page 1, try to navigate
        for t in tabs:
            if "popup" in t.get("url", "").lower() and t.get("webSocketDebuggerUrl"):
                popup_tab = t
                popup_ws = t["webSocketDebuggerUrl"]
                break
        if popup_tab:
            log("Found popup, navigating to page 2...")
            navigate_popup_page2()
            time.sleep(2)
        else:
            log("FATAL: No Follow-Up popup found at all!")
            return

    # Find the main SAP tab (the opp that owns this popup)
    main_tab = find_main_sap_tab(tabs)
    if not main_tab:
        log("ERROR: No main SAP opportunity tab found!")
        return
    log(f"Main tab: {main_tab['title'][:50]}")

    results_summary = []

    for row in range(start_row, end_row + 1):
        type_name = TYPES.get(row, f"unknown_{row}")
        log(f"\n{'='*60}")
        log(f"=== ROW {row}: {type_name} ===")
        log(f"{'='*60}")

        # Step 1: Click the type in popup
        if not click_type_in_popup(row):
            log(f"  FAILED to click row {row}. Skipping.")
            results_summary.append({"row": row, "name": type_name, "status": "CLICK_FAILED"})
            continue

        # Step 2: Wait and scan the main window
        time.sleep(3)  # Extra wait for form to load
        tabs = get_tabs()  # Refresh tabs
        main_tab = find_main_sap_tab(tabs)
        if not main_tab:
            log("  ERROR: Lost main tab after click!")
            results_summary.append({"row": row, "name": type_name, "status": "NO_MAIN_TAB"})
            continue

        data = scan_main_window(main_tab)
        if not data:
            log(f"  ERROR: Scan returned no data for {type_name}")
            results_summary.append({"row": row, "name": type_name, "status": "SCAN_FAILED"})
        else:
            nf = len(data.get("fields", []))
            ns = len(data.get("spans", []))
            nb = len(data.get("buttons", []))
            nd = len(data.get("dropdowns", []))
            nc = len(data.get("checkboxes", []))
            nt = len(data.get("tabs", []))
            log(f"  SCANNED: {nf} fields, {ns} spans, {nb} buttons, {nd} dropdowns, {nc} checkboxes, {nt} tabs")

            # Save playbook
            playbook = {
                "screen": f"followup_{type_name}",
                "description": f"Form opened after selecting '{type_name}' (row {row}) from Follow-Up popup",
                "followup_row": row,
                "followup_type": type_name,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "mode": "CREATE",
                "source_tab": main_tab.get("title", "")[:80],
                **data
            }

            # Clean junk
            playbook["fields"] = [f for f in playbook.get("fields", [])
                                  if f.get("stable_suffix") not in ("SavedSearches", "QUICKSEARCH", "")]

            filename = f"playbook_followup_{type_name.lower()}.json"
            outpath = OUTPUT_DIR / filename
            with open(outpath, "w", encoding="utf-8") as f:
                json.dump(playbook, f, indent=2, ensure_ascii=False)
            log(f"  SAVED: {filename} ({outpath.stat().st_size:,} bytes)")

            results_summary.append({
                "row": row, "name": type_name, "status": "OK",
                "fields": nf, "spans": ns, "buttons": nb, "dropdowns": nd,
                "file": filename
            })

        # Step 3: Cancel and go back
        log(f"  Canceling form...")
        tabs = get_tabs()
        main_tab = find_main_sap_tab(tabs)
        if main_tab:
            cancel_and_return(main_tab)
        time.sleep(2)

        # Step 4: Reopen Follow-Up popup (except after last row)
        if row < end_row:
            log(f"  Reopening Follow-Up popup...")
            tabs = get_tabs()
            main_tab = find_main_sap_tab(tabs)
            if main_tab:
                reopen_followup(main_tab)
                time.sleep(3)
                # Navigate to page 2
                navigate_popup_page2()
                time.sleep(2)

    # Final summary
    log(f"\n{'='*60}")
    log("=== SUMMARY ===")
    log(f"{'='*60}")
    ok = sum(1 for r in results_summary if r.get("status") == "OK")
    log(f"Scanned: {ok}/{len(results_summary)}")
    for r in results_summary:
        status = r["status"]
        if status == "OK":
            log(f"  [{status}] Row {r['row']}: {r['name']} -> {r['fields']} fields, {r['spans']} spans | {r['file']}")
        else:
            log(f"  [{status}] Row {r['row']}: {r['name']}")

    # Save summary
    summary_path = OUTPUT_DIR / "followup_scan_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)
    log(f"\nSummary saved: {summary_path}")


if __name__ == "__main__":
    main()
