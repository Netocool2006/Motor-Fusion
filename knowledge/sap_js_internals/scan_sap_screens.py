"""
scan_sap_screens.py — Escanea pantallas de SAP CRM y genera playbooks JSON
Conecta via CDP al Chrome con sesión SAP activa.
Detecta popups via CDP Target.getTargets.

Uso:
  python scan_sap_screens.py

Requiere: Chrome corriendo con --remote-debugging-port=9222 y SAP logueado.
"""
import json
import time
import sys
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP_PORT = 9222
OUTPUT_DIR = Path(__file__).parent / "playbooks"
OUTPUT_DIR.mkdir(exist_ok=True)

# SAP credentials for HTTP auth
SAP_USER = "ntoledo"
HTTP_USER = "ntoledo"
HTTP_PASS = "Gbmcr2026"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_work_frame(page):
    """Navigate through SAP iframe chain to get WorkAreaFrame1 content."""
    for fr in page.frames:
        if "WorkAreaFrame1" in (fr.name or "") or "WorkAreaFrame1popup" in (fr.name or ""):
            return fr
    # Fallback: try finding by URL pattern
    for fr in page.frames:
        url = fr.url or ""
        if "popup_buffered_frame" in url or "WorkAreaFrame" in (fr.name or ""):
            return fr
    return None


def scan_fields(frame):
    """Extract all visible input fields with stable suffixes."""
    return frame.evaluate("""() => {
        const fields = [];
        document.querySelectorAll('input[type="text"], input:not([type]), textarea, select').forEach(el => {
            if (el.offsetParent === null && el.type !== 'hidden') return;
            const id = el.id || '';
            const stableSuffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
            if (!stableSuffix || stableSuffix.startsWith('htmlb') || stableSuffix.includes('_isExpanded') ||
                stableSuffix.includes('_iscollapsed') || stableSuffix === 'SavedSearches') return;

            let label = '';
            try {
                const td = el.closest('td');
                if (td && td.previousElementSibling) {
                    label = td.previousElementSibling.textContent.trim().replace(/^[\\*\\s]+/, '').replace(/[:\\s]+$/, '');
                    if (label.length > 50) label = '';
                }
            } catch(e) {}

            fields.push({
                stable_suffix: stableSuffix,
                selector: '[id$="' + stableSuffix + '"]',
                label: label,
                value: (el.value || '').substring(0, 60),
                type: el.tagName === 'SELECT' ? 'dropdown' : el.tagName === 'TEXTAREA' ? 'textarea' : 'input',
                editable: !el.readOnly && !el.disabled,
                visible: el.offsetParent !== null
            });
        });
        return fields;
    }""")


def scan_spans(frame):
    """Extract read-only span values with stable suffixes."""
    return frame.evaluate("""() => {
        const spans = [];
        document.querySelectorAll('span, a').forEach(el => {
            const id = el.id || '';
            const stableSuffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
            if (!stableSuffix || stableSuffix.startsWith('htmlb') || stableSuffix.includes('Expanded')) return;
            const text = (el.textContent || '').trim();
            if (!text || text.length > 100 || el.offsetParent === null) return;

            let label = '';
            try {
                const td = el.closest('td');
                if (td && td.previousElementSibling) {
                    label = td.previousElementSibling.textContent.trim().replace(/^[\\*\\s]+/, '').replace(/[:\\s]+$/, '');
                    if (label.length > 50) label = '';
                }
            } catch(e) {}

            spans.push({ stable_suffix: stableSuffix, label: label, value: text.substring(0, 60) });
        });
        // Deduplicate
        const seen = new Set();
        return spans.filter(s => { if (seen.has(s.stable_suffix)) return false; seen.add(s.stable_suffix); return true; });
    }""")


def scan_buttons(frame):
    """Extract action buttons with stable suffixes."""
    return frame.evaluate("""() => {
        const btns = [];
        const navItems = ['Home','Account Management','Activities','Sales Cycle','Master Data',
            'Service Orders','Service Contracts','Accounts','Contacts','Reporte ZSD_ESP',
            'Reporte de precios ESP','Forecast GBM','Forecast Employee GBM'];

        document.querySelectorAll('a[onclick], button, input[type="button"]').forEach(el => {
            const text = (el.textContent || el.value || '').trim();
            if (!text || text.length > 50 || text.length < 2) return;
            if (navItems.includes(text)) return;
            const id = el.id || '';
            const stableSuffix = id.replace(/^(C\\d+_W\\d+_(?:V\\d+_)*)/g, '');
            btns.push({ text: text, stable_suffix: stableSuffix });
        });
        const seen = new Set();
        return btns.filter(b => { const k = b.text; if (seen.has(k)) return false; seen.add(k); return true; });
    }""")


def scan_table_columns(frame):
    """Extract table structures (Items, Contacts, etc.)."""
    return frame.evaluate("""() => {
        const tables = [];
        document.querySelectorAll('table').forEach(tbl => {
            const headerRow = tbl.querySelector('tr');
            if (!headerRow) return;
            const headers = [];
            headerRow.querySelectorAll('th, td').forEach(cell => {
                const text = (cell.textContent || '').trim();
                if (text && text.length < 40) headers.push(text);
            });
            if (headers.length >= 3 && headers.length <= 20) {
                // Find a section title nearby
                let title = '';
                try {
                    let prev = tbl.parentElement;
                    for (let i = 0; i < 5 && prev; i++) {
                        const hd = prev.querySelector('.th-tp-hd, legend, h3, h4');
                        if (hd) { title = hd.textContent.trim(); break; }
                        prev = prev.parentElement;
                    }
                } catch(e) {}
                tables.push({ title: title.substring(0, 40), columns: headers });
            }
        });
        // Deduplicate by title
        const seen = new Set();
        return tables.filter(t => { if (!t.title || seen.has(t.title)) return false; seen.add(t.title); return true; });
    }""")


def scan_page(page, screen_name, is_edit=False):
    """Full scan of a SAP page — fields, spans, buttons, tables."""
    log(f"Scanning: {screen_name}")

    playbook = {
        "screen": screen_name,
        "title": page.title(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "iframe_chain": ["CRMApplicationFrame", "CRMApplicationFrame", "WorkAreaFrame1"],
        "mode": "EDIT" if is_edit else "VIEW",
        "fields": [],
        "read_only_values": [],
        "buttons": [],
        "tables": []
    }

    # Try all frames
    for fr in page.frames:
        try:
            frame_name = fr.name or ""
            # Skip very small frames
            fields = scan_fields(fr)
            if len(fields) > 3:  # Found content
                log(f"  Frame '{frame_name}': {len(fields)} fields")
                playbook["fields"].extend(fields)
                playbook["read_only_values"].extend(scan_spans(fr))
                playbook["buttons"].extend(scan_buttons(fr))
                playbook["tables"].extend(scan_table_columns(fr))
        except Exception as e:
            pass

    # Filter out nav-only fields
    playbook["fields"] = [f for f in playbook["fields"]
                          if f["stable_suffix"] not in ("SavedSearches", "QUICKSEARCH")]

    log(f"  Result: {len(playbook['fields'])} fields, {len(playbook['read_only_values'])} spans, "
        f"{len(playbook['buttons'])} buttons, {len(playbook['tables'])} tables")

    # Save
    filename = f"playbook_{screen_name.lower().replace(' ', '_').replace('-', '_')}.json"
    outpath = OUTPUT_DIR / filename
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(playbook, f, indent=2, ensure_ascii=False)
    log(f"  Saved: {outpath}")

    return playbook


def find_popup_pages(playwright_instance, browser, main_page):
    """Find popup windows via CDP Target.getTargets — same logic as login_sap_once2.py"""
    popup_pages = []

    # Method 1: Check context pages
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if pg != main_page and "about:blank" not in pg.url:
                popup_pages.append(pg)

    # Method 2: CDP Target.getTargets
    try:
        cdp = browser.new_browser_cdp_session()
        targets = cdp.send("Target.getTargets")
        main_urls = {main_page.url} | {pg.url for pg in popup_pages}

        for tgt in targets.get("targetInfos", []):
            turl = tgt.get("url", "")
            if turl and turl not in main_urls and "popup_buffered_frame" in turl:
                log(f"  CDP popup found: {turl[:80]}")
                # Connect to it
                try:
                    browser2 = playwright_instance.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                    for ctx2 in browser2.contexts:
                        for pg2 in ctx2.pages:
                            if "popup_buffered_frame" in (pg2.url or ""):
                                popup_pages.append(pg2)
                except Exception as e:
                    log(f"  CDP connect error: {e}")
        cdp.detach()
    except Exception as e:
        log(f"  CDP error: {e}")

    return popup_pages


def click_nav_link(work_frame, link_text):
    """Click a navigation link in SAP sidebar."""
    try:
        link = work_frame.locator(f"a:text-is('{link_text}')").first
        link.click()
        time.sleep(3)
        return True
    except:
        return False


def click_button_in_frame(page, button_text):
    """Click a button in any frame of the page."""
    for fr in page.frames:
        try:
            btn = fr.locator(f"a:text-is('{button_text}'), button:text-is('{button_text}')").first
            if btn.is_visible(timeout=2000):
                btn.click()
                return True
        except:
            pass
    return False


def main():
    log("=== SAP CRM Screen Scanner ===")
    log(f"Connecting to Chrome CDP on port {CDP_PORT}...")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        # Find the SAP tab among all open tabs
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "SAP" in pg.title() or "sap" in pg.url.lower():
                    page = pg
                    break
            if page:
                break
        if not page:
            log("ERROR: No SAP tab found! Open SAP CRM first.")
            return
        context = page.context

        log(f"Connected. Title: {page.title()}")
        log(f"URL: {page.url[:80]}")

        # Check if logged in
        title = page.title()
        if "Logon" in title or "logon" in title.lower():
            log("SAP login page detected — please log in first!")
            log("Waiting 30s for login...")
            deadline = time.time() + 30
            while time.time() < deadline:
                title = page.title()
                if "Logon" not in title and "logon" not in title.lower():
                    log(f"Logged in! Title: {title}")
                    break
                time.sleep(2)
            else:
                log("ERROR: Still on login page. Aborting.")
                return

        time.sleep(2)

        # ── SCAN 1: Current page (whatever is open) ──
        log("\n=== SCAN 1: Current page ===")
        scan_page(page, "current_page")

        # ── Navigate to Opportunities and scan ──
        log("\n=== SCAN 2: Opportunities Search ===")
        work_frame = get_work_frame(page)
        if work_frame and click_nav_link(work_frame, "Opportunities"):
            time.sleep(3)
            scan_page(page, "opportunities_search")

            # Search for opp 245372 and open it
            log("\n=== SCAN 3: Opportunity Detail (VIEW) ===")
            for fr in page.frames:
                try:
                    filled = fr.evaluate("""() => {
                        const field = document.querySelector('[aria-label*="value of criterion Opportunity ID"]');
                        if (field) { field.value = '245372'; field.dispatchEvent(new Event('change', {bubbles:true})); return true; }
                        return false;
                    }""")
                    if filled:
                        # Click Search
                        search_btn = fr.locator("a:text-is('Search'), button:text-is('Search')").first
                        search_btn.click()
                        time.sleep(3)

                        # Click result
                        result_link = fr.locator("a:text-matches('Agentes Virtuales')").first
                        result_link.click()
                        time.sleep(4)
                        break
                except:
                    pass

            scan_page(page, "opportunity_detail_view")

            # ── Click Edit and scan EDIT mode ──
            log("\n=== SCAN 4: Opportunity Detail (EDIT) ===")
            if click_button_in_frame(page, "Edit"):
                time.sleep(3)
                scan_page(page, "opportunity_detail_edit", is_edit=True)

                # Cancel edit
                click_button_in_frame(page, "Cancel")
                time.sleep(2)

            # ── Click Create Follow-Up and scan POPUP ──
            log("\n=== SCAN 5: Create Follow-Up POPUP ===")
            if click_button_in_frame(page, "Create Follow-Up"):
                time.sleep(5)  # SAP roundtrip + popup open

                # Find popup
                popups = find_popup_pages(p, browser, page)
                if popups:
                    for popup_pg in popups:
                        log(f"  Scanning popup: {popup_pg.title()}")
                        scan_page(popup_pg, "create_followup_popup")
                else:
                    # Maybe it's in an iframe within the same page
                    log("  No separate popup found — scanning current page frames...")
                    scan_page(page, "create_followup_inline")

        log("\n=== SCAN COMPLETE ===")
        log(f"Playbooks saved to: {OUTPUT_DIR}")

        # List generated files
        for f in sorted(OUTPUT_DIR.glob("*.json")):
            size = f.stat().st_size
            log(f"  {f.name} ({size:,} bytes)")


if __name__ == "__main__":
    main()
