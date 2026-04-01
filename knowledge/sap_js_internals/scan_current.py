"""
scan_current.py — Scan all currently open SAP pages/popups via CDP.
Saves each as a playbook JSON.

Usage: python scan_current.py
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
                data = json.loads(self.ws.recv())
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
        inner = result.get("result", {})
        return inner.get("value") if isinstance(inner, dict) else inner

    def close(self):
        try:
            self.ws.close()
        except:
            pass


SCAN_JS = r"""(() => {
    const result = {fields: [], spans: [], buttons: [], tables: [], dropdowns: [], checkboxes: []};

    // Fields
    document.querySelectorAll('input[type="text"], input:not([type]), textarea, select').forEach(el => {
        if (el.offsetParent === null && el.type !== 'hidden') return;
        const id = el.id || '';
        const suffix = id.replace(/^(C\d+_W\d+_(?:V\d+_)*)/g, '');
        if (!suffix || suffix.startsWith('htmlb') || suffix.includes('_isExpanded') ||
            suffix.includes('_iscollapsed') || suffix === 'SavedSearches') return;

        let label = '';
        try {
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                label = td.previousElementSibling.textContent.trim()
                    .replace(/^[\*\s]+/, '').replace(/[:\s]+$/, '');
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
        const suffix = id.replace(/^(C\d+_W\d+_(?:V\d+_)*)/g, '');
        if (!suffix) return;
        let label = '';
        try {
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                label = td.previousElementSibling.textContent.trim()
                    .replace(/^[\*\s]+/, '').replace(/[:\s]+$/, '');
                if (label.length > 50) label = '';
            }
        } catch(e) {}
        result.checkboxes.push({stable_suffix: suffix, label: label, checked: el.checked});
    });

    // Spans
    document.querySelectorAll('span[id], a[id]').forEach(el => {
        const id = el.id || '';
        const suffix = id.replace(/^(C\d+_W\d+_(?:V\d+_)*)/g, '');
        if (!suffix || suffix.startsWith('htmlb') || suffix.includes('Expanded')) return;
        const text = (el.textContent || '').trim();
        if (!text || text.length > 100 || el.offsetParent === null) return;
        let label = '';
        try {
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                label = td.previousElementSibling.textContent.trim()
                    .replace(/^[\*\s]+/, '').replace(/[:\s]+$/, '');
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
        const suffix = id.replace(/^(C\d+_W\d+_(?:V\d+_)*)/g, '');
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


def scan_target(tab_info, name):
    """Connect to a target and scan all its frames."""
    ws_url = tab_info.get("webSocketDebuggerUrl")
    title = tab_info.get("title", "?")
    if not ws_url:
        log(f"  No websocket for: {title[:40]}")
        return None

    log(f"Scanning: {title[:60]} -> '{name}'")
    cdp = CDPSession(ws_url, timeout=20)
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

    log(f"  {len(frames)} frames, {len(contexts)} contexts")
    for fid, finfo in frames.items():
        has = "Y" if fid in contexts else "N"
        log(f"    [{has}] {finfo['name'] or '(main)'} depth={finfo['depth']}")

    combined = {"fields": [], "spans": [], "buttons": [], "tables": [], "dropdowns": [], "checkboxes": []}
    for fid, finfo in frames.items():
        ctx_id = contexts.get(fid)
        if not ctx_id:
            continue
        try:
            data = cdp.evaluate(SCAN_JS, context_id=ctx_id)
            if data and isinstance(data, dict):
                nf = len(data.get("fields", []))
                ns = len(data.get("spans", []))
                if nf > 0 or ns > 0:
                    log(f"    Frame '{finfo['name']}': {nf} fields, {ns} spans, "
                        f"{len(data.get('buttons', []))} btns, {len(data.get('dropdowns', []))} ddl, "
                        f"{len(data.get('checkboxes', []))} chk")
                    for key in combined:
                        combined[key].extend(data.get(key, []))
        except Exception as e:
            log(f"    Error in frame '{finfo['name']}': {e}")

    playbook = {
        "screen": name,
        "description": f"Screen: {title[:80]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "SCAN",
        "tab_title": title,
        **combined
    }
    playbook["fields"] = [f for f in playbook["fields"]
                          if f.get("stable_suffix") not in ("SavedSearches", "QUICKSEARCH", "")]

    filename = f"playbook_{name}.json"
    outpath = OUTPUT_DIR / filename
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(playbook, f, indent=2, ensure_ascii=False)

    nf = len(playbook.get("fields", []))
    ns = len(playbook.get("spans", []))
    nb = len(playbook.get("buttons", []))
    nd = len(playbook.get("dropdowns", []))
    nc = len(playbook.get("checkboxes", []))
    log(f"  SAVED: {filename} -- {nf} fields, {ns} spans, {nb} btns, {nd} ddl, {nc} chk ({outpath.stat().st_size:,} bytes)")

    cdp.close()
    return playbook


def main():
    log("=== SAP Current Screen Scanner ===")

    tabs = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json').read())
    log(f"Found {len(tabs)} targets")

    for t in tabs:
        if t.get("type") != "page":
            continue
        title = t.get("title", "")
        url = t.get("url", "")
        if url.startswith("chrome"):
            continue

        # Determine name based on title
        if "Select Items" in title:
            name = "followup_select_items_popup"
        elif "Opport Standard: New" in title:
            name = "followup_opport_standard_new"
        elif "Quote" in title and "New" in title:
            name = "followup_quote_new"
        elif "Service" in title and "New" in title:
            name = "followup_service_new"
        elif "Task" in title and "New" in title:
            name = "followup_task_new"
        elif "Follow-Up" in title and "Select" not in title:
            name = "followup_popup"
            log(f"Skipping known Follow-Up popup: {title[:40]}")
            continue
        elif "245372" in title:
            log(f"Skipping known opp 245372: {title[:40]}")
            continue
        else:
            name = f"scan_{t['id'][:8].lower()}"

        log(f"\n--- {title[:60]} ---")
        scan_target(t, name)

    log("\n=== ALL DONE ===")


if __name__ == "__main__":
    main()
