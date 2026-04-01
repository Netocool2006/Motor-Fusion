"""
scan_cdp.py — Escanea pantallas SAP CRM via CDP puro (sin Playwright)
Conecta directo via websocket al Chrome con CDP habilitado.

Uso: python scan_cdp.py [--opp OPP_ID]
Requiere: Chrome con --remote-debugging-port=9222 y SAP logueado.
"""
import json
import time
import sys
import urllib.request
from pathlib import Path
import websocket

CDP_PORT = 9222
OUTPUT_DIR = Path(__file__).parent / "playbooks"
OUTPUT_DIR.mkdir(exist_ok=True)

OPP_ID = "245372"  # Default opportunity to scan
if "--opp" in sys.argv:
    idx = sys.argv.index("--opp")
    if idx + 1 < len(sys.argv):
        OPP_ID = sys.argv[idx + 1]

msg_counter = 0

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_tabs():
    """Get all Chrome tabs via CDP HTTP endpoint."""
    resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json')
    return json.loads(resp.read())


def get_browser_ws():
    """Get browser-level websocket URL."""
    resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/version')
    info = json.loads(resp.read())
    return info.get("webSocketDebuggerUrl")


class CDPSession:
    """Simple CDP session via raw websocket."""

    def __init__(self, ws_url, timeout=30):
        self.ws = websocket.create_connection(ws_url, timeout=timeout)
        self.msg_id = 0
        self.events = []

    def send(self, method, params=None):
        """Send CDP command and wait for response."""
        self.msg_id += 1
        mid = self.msg_id
        msg = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))

        # Wait for matching response (collect events along the way)
        deadline = time.time() + 30
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
                    # It's an event, store it
                    self.events.append(data)
            except websocket.WebSocketTimeoutException:
                continue
        return {"__error": "timeout"}

    def evaluate(self, expression, context_id=None, return_by_value=True):
        """Evaluate JS expression, optionally in a specific execution context."""
        params = {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": True,
            "timeout": 15000
        }
        if context_id:
            params["contextId"] = context_id
        result = self.send("Runtime.evaluate", params)
        if "__error" in result:
            return None
        exc = result.get("exceptionDetails")
        if exc:
            return None
        val = result.get("result", {})
        return val.get("value") if return_by_value else val

    def close(self):
        try:
            self.ws.close()
        except:
            pass


def find_sap_tab():
    """Find the SAP CRM tab."""
    tabs = get_tabs()
    for t in tabs:
        if t.get("type") == "page" and ("SAP" in t.get("title", "") or "sap" in t.get("url", "").lower()):
            if "chrome-extension" not in t.get("url", ""):
                return t
    return None


def get_frame_contexts(cdp):
    """Enable Runtime and collect execution contexts for all frames."""
    # Enable needed domains
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    time.sleep(1)

    # Get frame tree
    tree = cdp.send("Page.getFrameTree")
    frames = {}

    def walk_tree(node, depth=0):
        f = node.get("frame", {})
        fid = f.get("id", "")
        fname = f.get("name", "")
        furl = f.get("url", "")
        frames[fid] = {"name": fname, "url": furl, "depth": depth}
        for child in node.get("childFrames", []):
            walk_tree(child, depth + 1)

    if "frameTree" in tree:
        walk_tree(tree["frameTree"])

    # Collect execution contexts from events
    contexts = {}
    for ev in cdp.events:
        if ev.get("method") == "Runtime.executionContextCreated":
            ctx = ev["params"].get("context", {})
            aux = ctx.get("auxData", {})
            fid = aux.get("frameId", "")
            if fid and not aux.get("isDefault") == False:
                contexts[fid] = ctx.get("id")

    # Also try to query for them
    cdp.events.clear()

    return frames, contexts


def eval_in_frame(cdp, frame_id, contexts, expression):
    """Evaluate JS in a specific frame context."""
    ctx_id = contexts.get(frame_id)
    if ctx_id:
        return cdp.evaluate(expression, context_id=ctx_id)
    return None


def scan_via_js(cdp, contexts, frames):
    """Scan SAP fields by evaluating JS in each frame. Returns combined results."""

    SCAN_JS = """(() => {
        const result = {fields: [], spans: [], buttons: [], tables: []};

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

            result.fields.push({
                stable_suffix: suffix,
                selector: '[id$="' + suffix + '"]',
                label: label,
                value: (el.value || '').substring(0, 60),
                type: el.tagName === 'SELECT' ? 'dropdown' : el.tagName === 'TEXTAREA' ? 'textarea' : 'input',
                editable: !el.readOnly && !el.disabled,
                visible: el.offsetParent !== null
            });
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
        document.querySelectorAll('a[onclick], button, input[type="button"]').forEach(el => {
            const text = (el.textContent || el.value || '').trim();
            if (!text || text.length > 50 || text.length < 2) return;
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
            if (headers.length >= 3 && headers.length <= 20) {
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
        const seen_t = new Set();
        result.tables = result.tables.filter(t => {
            if (!t.title || seen_t.has(t.title)) return false;
            seen_t.add(t.title); return true;
        });

        return result;
    })()"""

    combined = {"fields": [], "spans": [], "buttons": [], "tables": []}

    for fid, finfo in frames.items():
        ctx_id = contexts.get(fid)
        if not ctx_id:
            continue

        try:
            data = cdp.evaluate(SCAN_JS, context_id=ctx_id)
            if data and isinstance(data, dict):
                nf = len(data.get("fields", []))
                if nf > 0:
                    log(f"  Frame '{finfo['name']}' (depth {finfo['depth']}): {nf} fields, "
                        f"{len(data.get('spans',[]))} spans, {len(data.get('buttons',[]))} buttons")
                    combined["fields"].extend(data["fields"])
                    combined["spans"].extend(data["spans"])
                    combined["buttons"].extend(data["buttons"])
                    combined["tables"].extend(data["tables"])
        except Exception as e:
            pass

    return combined


def click_in_frames(cdp, contexts, frames, selector_or_text, by="text"):
    """Click an element in SAP frames. Returns True if clicked."""
    if by == "text":
        js = f"""(() => {{
            const links = document.querySelectorAll('a, button, input[type="button"]');
            for (const el of links) {{
                const txt = (el.textContent || el.value || '').trim();
                if (txt === '{selector_or_text}') {{
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()"""
    else:
        js = f"""(() => {{
            const el = document.querySelector('{selector_or_text}');
            if (el) {{ el.click(); return true; }}
            return false;
        }})()"""

    for fid, finfo in frames.items():
        ctx_id = contexts.get(fid)
        if not ctx_id:
            continue
        try:
            result = cdp.evaluate(js, context_id=ctx_id)
            if result:
                return True
        except:
            pass
    return False


def save_playbook(name, data, mode="VIEW"):
    """Save scan results as a playbook JSON file."""
    playbook = {
        "screen": name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        **data
    }

    # Filter junk
    playbook["fields"] = [f for f in playbook.get("fields", [])
                          if f.get("stable_suffix") not in ("SavedSearches", "QUICKSEARCH", "")]

    filename = f"playbook_{name.lower().replace(' ', '_').replace('-', '_')}.json"
    outpath = OUTPUT_DIR / filename
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(playbook, f, indent=2, ensure_ascii=False)

    nf = len(playbook.get("fields", []))
    ns = len(playbook.get("spans", []))
    nb = len(playbook.get("buttons", []))
    nt = len(playbook.get("tables", []))
    log(f"  Saved {outpath.name}: {nf} fields, {ns} spans, {nb} buttons, {nt} tables")
    return playbook


def refresh_contexts(cdp):
    """Re-enable Runtime to get fresh execution contexts after navigation."""
    cdp.events.clear()
    cdp.send("Runtime.disable")
    time.sleep(0.5)
    cdp.send("Runtime.enable")
    time.sleep(1.5)

    tree = cdp.send("Page.getFrameTree")
    frames = {}

    def walk_tree(node, depth=0):
        f = node.get("frame", {})
        fid = f.get("id", "")
        fname = f.get("name", "")
        furl = f.get("url", "")
        frames[fid] = {"name": fname, "url": furl, "depth": depth}
        for child in node.get("childFrames", []):
            walk_tree(child, depth + 1)

    if "frameTree" in tree:
        walk_tree(tree["frameTree"])

    contexts = {}
    for ev in cdp.events:
        if ev.get("method") == "Runtime.executionContextCreated":
            ctx = ev["params"].get("context", {})
            aux = ctx.get("auxData", {})
            fid = aux.get("frameId", "")
            is_default = aux.get("isDefault", True)
            if fid and is_default:
                contexts[fid] = ctx.get("id")

    return frames, contexts


def scan_popup_targets():
    """Use browser-level CDP to find popup windows."""
    browser_ws = get_browser_ws()
    if not browser_ws:
        return []

    try:
        bcdp = CDPSession(browser_ws, timeout=10)
        result = bcdp.send("Target.getTargets")
        bcdp.close()

        popups = []
        for tgt in result.get("targetInfos", []):
            url = tgt.get("url", "")
            ttype = tgt.get("type", "")
            if ttype == "page" and "popup_buffered_frame" in url:
                popups.append(tgt)
        return popups
    except Exception as e:
        log(f"  Popup scan error: {e}")
        return []


def main():
    log("=== SAP CRM Screen Scanner (CDP Pure) ===")

    # Find SAP tab
    sap_tab = find_sap_tab()
    if not sap_tab:
        log("ERROR: No SAP tab found! Open SAP CRM first.")
        return

    ws_url = sap_tab["webSocketDebuggerUrl"]
    log(f"SAP tab: {sap_tab['title']}")
    log(f"Connecting to: {ws_url[:60]}...")

    cdp = CDPSession(ws_url, timeout=30)
    log("Connected!")

    # Enable domains
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    cdp.send("DOM.enable")
    time.sleep(2)

    frames, contexts = get_frame_contexts(cdp)
    log(f"Found {len(frames)} frames, {len(contexts)} execution contexts")

    for fid, finfo in frames.items():
        has_ctx = "Y" if fid in contexts else "N"
        log(f"  [{has_ctx}] {finfo['name'] or '(main)'} depth={finfo['depth']}")

    # ── SCAN 1: Home page ──
    title = cdp.evaluate("document.title")
    log(f"\n=== SCAN 1: Home ({title}) ===")
    data = scan_via_js(cdp, contexts, frames)
    save_playbook("sap_home", data)

    # ── Navigate to Sales Cycle > Opportunities ──
    log("\n=== Navigating to Opportunities... ===")

    # Click in nav - SAP uses a navigation bar with links
    nav_clicked = False
    for fid, finfo in frames.items():
        ctx_id = contexts.get(fid)
        if not ctx_id:
            continue
        result = cdp.evaluate("""(() => {
            // Look for "Sales Cycle" or "Opportunities" in navigation
            const links = document.querySelectorAll('a');
            for (const a of links) {
                const txt = a.textContent.trim();
                if (txt === 'Sales Cycle') {
                    a.click();
                    return 'Sales Cycle clicked';
                }
            }
            // Direct try
            for (const a of links) {
                const txt = a.textContent.trim();
                if (txt === 'Opportunities') {
                    a.click();
                    return 'Opportunities clicked';
                }
            }
            return null;
        })()""", context_id=ctx_id)
        if result:
            log(f"  {result}")
            nav_clicked = True
            break

    if nav_clicked:
        time.sleep(4)
        frames, contexts = refresh_contexts(cdp)
        log(f"  After nav: {len(frames)} frames, {len(contexts)} contexts")

        # If we clicked Sales Cycle, now click Opportunities
        for fid, finfo in frames.items():
            ctx_id = contexts.get(fid)
            if not ctx_id:
                continue
            result = cdp.evaluate("""(() => {
                const links = document.querySelectorAll('a');
                for (const a of links) {
                    if (a.textContent.trim() === 'Opportunities') {
                        a.click();
                        return true;
                    }
                }
                return false;
            })()""", context_id=ctx_id)
            if result:
                log("  Opportunities clicked")
                break

        time.sleep(4)
        frames, contexts = refresh_contexts(cdp)

    # ── SCAN 2: Opportunities Search ──
    log("\n=== SCAN 2: Opportunities Search ===")
    data = scan_via_js(cdp, contexts, frames)
    save_playbook("opportunities_search", data)

    # ── Navigate to specific opportunity ──
    log(f"\n=== Opening OPP {OPP_ID}... ===")
    opp_opened = False

    # Strategy 1: Click from Recent Items (faster, no search needed)
    for fid, finfo in frames.items():
        ctx_id = contexts.get(fid)
        if not ctx_id:
            continue
        result = cdp.evaluate(f"""(() => {{
            // Look for OPP ID in Recent Items links
            const links = document.querySelectorAll('a');
            for (const a of links) {{
                const txt = a.textContent.trim();
                if (txt.startsWith('{OPP_ID}')) {{
                    a.click();
                    return 'Recent Item clicked: ' + txt.substring(0, 50);
                }}
            }}
            return null;
        }})()""", context_id=ctx_id)
        if result:
            log(f"  {result}")
            opp_opened = True
            break

    # Strategy 2: Use search form with correct selectors
    if not opp_opened:
        log("  Not in Recent Items, using search form...")
        for fid, finfo in frames.items():
            ctx_id = contexts.get(fid)
            if not ctx_id:
                continue
            result = cdp.evaluate(f"""(() => {{
                // Use stable suffix selector for VALUE1 field
                const field = document.querySelector('[id$="search_parameters[1].VALUE1"]');
                if (field) {{
                    field.focus();
                    field.value = '{OPP_ID}';
                    field.dispatchEvent(new Event('input', {{bubbles: true}}));
                    field.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled VALUE1: ' + field.id;
                }}
                return null;
            }})()""", context_id=ctx_id)
            if result:
                log(f"  {result}")
                time.sleep(1)
                # Click Search button using stable suffix
                cdp.evaluate("""(() => {
                    const btn = document.querySelector('[id$="Searchbtn"]');
                    if (btn) { btn.click(); return true; }
                    return false;
                })()""", context_id=ctx_id)
                log("  Search clicked")
                time.sleep(5)
                frames, contexts = refresh_contexts(cdp)

                # Click first result in search results table
                for fid2, finfo2 in frames.items():
                    ctx_id2 = contexts.get(fid2)
                    if not ctx_id2:
                        continue
                    result2 = cdp.evaluate(f"""(() => {{
                        // Search results are in a table. Find link containing OPP ID
                        const links = document.querySelectorAll('a');
                        for (const a of links) {{
                            const txt = a.textContent.trim();
                            if (txt.includes('{OPP_ID}') || txt.startsWith('{OPP_ID}')) {{
                                a.click();
                                return 'Result clicked: ' + txt.substring(0, 50);
                            }}
                        }}
                        // Fallback: click first result that looks like an opp link
                        const resultLinks = document.querySelectorAll('a[id$="1"]');
                        for (const a of resultLinks) {{
                            const txt = a.textContent.trim();
                            if (txt.length > 5 && txt.length < 80 && !['Search','Cancel','Clear','Save','New','Back'].includes(txt)) {{
                                a.click();
                                return 'Fallback clicked: ' + txt.substring(0, 50);
                            }}
                        }}
                        return null;
                    }})()""", context_id=ctx_id2)
                    if result2:
                        log(f"  {result2}")
                        opp_opened = True
                        break
                break

    if opp_opened:
        time.sleep(5)
        frames, contexts = refresh_contexts(cdp)

    # ── SCAN 3: Opportunity Detail VIEW ──
    log("\n=== SCAN 3: Opportunity Detail (VIEW) ===")
    data = scan_via_js(cdp, contexts, frames)
    save_playbook("opportunity_detail_view", data)

    # ── Click Edit ──
    log("\n=== Clicking Edit... ===")
    edit_clicked = click_in_frames(cdp, contexts, frames, "Edit")
    if edit_clicked:
        log("  Edit clicked")
        time.sleep(4)
        frames, contexts = refresh_contexts(cdp)

        # ── SCAN 4: Opportunity Detail EDIT ──
        log("\n=== SCAN 4: Opportunity Detail (EDIT) ===")
        data = scan_via_js(cdp, contexts, frames)
        save_playbook("opportunity_detail_edit", data, mode="EDIT")

        # Cancel edit
        log("  Cancelling edit...")
        click_in_frames(cdp, contexts, frames, "Cancel")
        time.sleep(3)
        frames, contexts = refresh_contexts(cdp)
    else:
        log("  Edit button not found")

    # ── Click Create Follow-Up ──
    log("\n=== SCAN 5: Create Follow-Up POPUP ===")
    fu_clicked = click_in_frames(cdp, contexts, frames, "Create Follow-Up")
    if fu_clicked:
        log("  Create Follow-Up clicked, waiting for popup...")
        time.sleep(6)

        # Check for popup via Target.getTargets on browser-level CDP
        popups = scan_popup_targets()

        if popups:
            for popup in popups:
                purl = popup.get("url", "")
                log(f"  Popup found: {purl[:80]}")

                # Connect to popup page
                # Find the popup tab in /json
                tabs = get_tabs()
                for t in tabs:
                    if "popup_buffered_frame" in t.get("url", ""):
                        log(f"  Connecting to popup tab...")
                        pcdp = CDPSession(t["webSocketDebuggerUrl"], timeout=15)
                        pcdp.send("Page.enable")
                        pcdp.send("Runtime.enable")
                        time.sleep(2)

                        pframes, pcontexts = refresh_contexts.__wrapped__(pcdp) if hasattr(refresh_contexts, '__wrapped__') else _refresh(pcdp)
                        pdata = scan_via_js(pcdp, pcontexts, pframes)
                        save_playbook("create_followup_popup", pdata)
                        pcdp.close()
                        break
        else:
            # Maybe popup is a new tab or inline
            log("  No separate popup detected via CDP targets")

            # Check for new tabs
            tabs = get_tabs()
            for t in tabs:
                url = t.get("url", "")
                title = t.get("title", "")
                if t.get("type") == "page" and "popup" in url.lower():
                    log(f"  Found popup tab: {title}")
                    pcdp = CDPSession(t["webSocketDebuggerUrl"], timeout=15)
                    pcdp.send("Page.enable")
                    pcdp.send("Runtime.enable")
                    time.sleep(2)
                    pframes, pcontexts = _refresh(pcdp)
                    pdata = scan_via_js(pcdp, pcontexts, pframes)
                    save_playbook("create_followup_popup", pdata)
                    pcdp.close()
                    break
            else:
                # Check inline — refresh main page frames
                frames, contexts = refresh_contexts(cdp)
                log(f"  Checking inline popup ({len(frames)} frames)...")
                data = scan_via_js(cdp, contexts, frames)
                save_playbook("create_followup_inline", data)
    else:
        log("  Create Follow-Up button not found")

    # ── Summary ──
    log("\n=== SCAN COMPLETE ===")
    log(f"Playbooks saved to: {OUTPUT_DIR}")
    for f in sorted(OUTPUT_DIR.glob("playbook_*.json")):
        size = f.stat().st_size
        with open(f, "r", encoding="utf-8") as fh:
            pb = json.load(fh)
        nf = len(pb.get("fields", []))
        log(f"  {f.name} — {size:,} bytes, {nf} fields")

    cdp.close()
    log("Done.")


def _refresh(cdp):
    """Standalone refresh_contexts for popup CDPSessions."""
    cdp.events.clear()
    cdp.send("Runtime.disable")
    time.sleep(0.5)
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


if __name__ == "__main__":
    main()
