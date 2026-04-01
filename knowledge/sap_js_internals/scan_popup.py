"""
scan_popup.py — Escanea el popup Follow-Up de SAP via CDP puro
Solo escanea lo que esté abierto (sin navegar).

Uso: python scan_popup.py
"""
import json
import time
import urllib.request
from pathlib import Path
import websocket

CDP_PORT = 9222
OUTPUT_DIR = Path(__file__).parent / "playbooks"
OUTPUT_DIR.mkdir(exist_ok=True)

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def get_tabs():
    resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json')
    return json.loads(resp.read())

def get_browser_ws():
    resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/version')
    return json.loads(resp.read()).get("webSocketDebuggerUrl")

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
        return result.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except:
            pass

SCAN_JS = """(() => {
    const result = {fields: [], spans: [], buttons: [], tables: [], dropdowns: []};

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

        // For dropdowns, capture options
        if (el.tagName === 'SELECT') {
            entry.options = [];
            el.querySelectorAll('option').forEach(opt => {
                entry.options.push({value: opt.value, text: opt.textContent.trim()});
            });
            result.dropdowns.push(entry);
        }

        result.fields.push(entry);
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


def scan_tab(tab_info, name):
    """Connect to a tab and scan its frames."""
    ws_url = tab_info.get("webSocketDebuggerUrl")
    if not ws_url:
        log(f"  No websocket URL for tab: {tab_info.get('title','?')}")
        return None

    log(f"Connecting to: {tab_info['title'][:50]}...")
    cdp = CDPSession(ws_url, timeout=20)

    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    time.sleep(1.5)

    # Get frame tree
    tree = cdp.send("Page.getFrameTree")
    frames = {}
    def walk(node, depth=0):
        f = node.get("frame", {})
        fid = f.get("id", "")
        frames[fid] = {"name": f.get("name",""), "url": f.get("url",""), "depth": depth}
        for child in node.get("childFrames", []):
            walk(child, depth+1)
    if "frameTree" in tree:
        walk(tree["frameTree"])

    # Get execution contexts
    contexts = {}
    for ev in cdp.events:
        if ev.get("method") == "Runtime.executionContextCreated":
            ctx = ev["params"].get("context", {})
            aux = ctx.get("auxData", {})
            fid = aux.get("frameId", "")
            if fid and aux.get("isDefault", True):
                contexts[fid] = ctx.get("id")

    log(f"  {len(frames)} frames, {len(contexts)} contexts")
    for fid, finfo in frames.items():
        has = "Y" if fid in contexts else "N"
        log(f"    [{has}] {finfo['name'] or '(main)'} depth={finfo['depth']}")

    # Scan all frames
    combined = {"fields": [], "spans": [], "buttons": [], "tables": [], "dropdowns": []}
    for fid, finfo in frames.items():
        ctx_id = contexts.get(fid)
        if not ctx_id:
            continue
        try:
            data = cdp.evaluate(SCAN_JS, context_id=ctx_id)
            if data and isinstance(data, dict):
                nf = len(data.get("fields", []))
                if nf > 0:
                    log(f"    Frame '{finfo['name']}': {nf} fields, {len(data.get('spans',[]))} spans, "
                        f"{len(data.get('buttons',[]))} btns, {len(data.get('dropdowns',[]))} ddl")
                    for key in combined:
                        combined[key].extend(data.get(key, []))
        except Exception as e:
            log(f"    Error in frame '{finfo['name']}': {e}")

    # Save
    playbook = {
        "screen": name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "SCAN",
        "tab_title": tab_info.get("title", ""),
        "tab_url": tab_info.get("url", "")[:120],
        **combined
    }
    playbook["fields"] = [f for f in playbook["fields"]
                          if f.get("stable_suffix") not in ("SavedSearches", "QUICKSEARCH", "")]

    filename = f"playbook_{name.lower().replace(' ', '_').replace('-','_')}.json"
    outpath = OUTPUT_DIR / filename
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(playbook, f, indent=2, ensure_ascii=False)

    nf = len(playbook.get("fields",[]))
    ns = len(playbook.get("spans",[]))
    nb = len(playbook.get("buttons",[]))
    nd = len(playbook.get("dropdowns",[]))
    log(f"  SAVED: {outpath.name} -- {nf} fields, {ns} spans, {nb} buttons, {nd} dropdowns")

    cdp.close()
    return playbook


def main():
    log("=== SAP Popup/Screen Scanner ===")

    # List ALL tabs/targets
    tabs = get_tabs()
    log(f"Found {len(tabs)} targets:")
    page_tabs = []
    for t in tabs:
        ttype = t.get("type", "?")
        title = t.get("title", "?")[:50]
        url = t.get("url", "")[:80]
        log(f"  [{ttype}] {title}")
        log(f"           {url}")
        if ttype == "page" and not url.startswith("chrome"):
            page_tabs.append(t)

    # Also check for popup targets via browser CDP
    browser_ws = get_browser_ws()
    if browser_ws:
        try:
            bcdp = CDPSession(browser_ws, timeout=10)
            result = bcdp.send("Target.getTargets")
            bcdp.close()
            for tgt in result.get("targetInfos", []):
                turl = tgt.get("url", "")
                ttitle = tgt.get("title", "")
                ttype = tgt.get("type", "")
                if ttype == "page" and "popup" in turl.lower():
                    log(f"  [CDP TARGET] {ttitle[:40]} | {turl[:60]}")
                    # Check if we already have this in page_tabs
                    if not any(t.get("url") == turl for t in page_tabs):
                        # Try to find its websocket URL from /json
                        for t2 in tabs:
                            if t2.get("url") == turl:
                                page_tabs.append(t2)
                                break
        except Exception as e:
            log(f"  CDP target scan error: {e}")

    if not page_tabs:
        log("ERROR: No scannable pages found!")
        return

    # Scan all non-chrome pages
    log(f"\n=== Scanning {len(page_tabs)} page(s) ===")
    for i, tab in enumerate(page_tabs):
        title = tab.get("title", "unknown")
        url = tab.get("url", "")

        # Determine name
        if "popup" in url.lower() or "popup" in title.lower():
            name = f"popup_{i}"
        elif "SAP" in title:
            name = "sap_main"
        elif "Asistente" in title:
            name = "asistente_ia"
        else:
            name = f"page_{i}"

        log(f"\n--- Scanning: {title[:50]} as '{name}' ---")
        scan_tab(tab, name)

    log("\n=== ALL DONE ===")
    for f in sorted(OUTPUT_DIR.glob("playbook_*.json")):
        with open(f, "r", encoding="utf-8") as fh:
            pb = json.load(fh)
        nf = len(pb.get("fields", []))
        log(f"  {f.name} -- {nf} fields, {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
