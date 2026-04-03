"""Login to NotebookLM via Playwright.
Opens Chromium, waits for user to login to Google, auto-saves cookies.
NO input() needed - polls URL automatically.
"""
import asyncio
import sys
import json
import time
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

from playwright.sync_api import sync_playwright

STORAGE_PATH = Path(r"C:\Users\ntoledo\AppData\Local\ClaudeCode\.notebooklm\storage_state.json")
BROWSER_PROFILE = Path(r"C:\Users\ntoledo\AppData\Local\ClaudeCode\.notebooklm\browser_profile")
BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

print("=== NotebookLM Login ===")
print("Opening browser... Log in with your Google account.")
print("The script will auto-detect when you reach NotebookLM.\n")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE),
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--password-store=basic",
        ],
        ignore_default_args=["--enable-automation"],
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://notebooklm.google.com/", wait_until="load", timeout=15000)

    print(f"Current URL: {page.url}")

    if "notebooklm.google.com" in page.url and "accounts.google.com" not in page.url:
        print("[OK] Already logged in!")
    else:
        print("Waiting for you to complete Google login...")
        print("(Will check every 3 seconds for up to 5 minutes)\n")

        for i in range(100):  # 5 min max
            time.sleep(3)
            try:
                url = page.url
                if "notebooklm.google.com" in url and "accounts.google.com" not in url:
                    print(f"\n[OK] Detected NotebookLM page! URL: {url}")
                    break
                if i % 10 == 0 and i > 0:
                    print(f"  Still waiting... ({i*3}s) URL: {url[:80]}")
            except:
                pass
        else:
            print("[TIMEOUT] Could not detect NotebookLM login after 5 minutes")
            context.close()
            sys.exit(1)

    # Force cookie collection from base domain
    page.goto("https://accounts.google.com/", wait_until="commit")
    page.goto("https://notebooklm.google.com/", wait_until="commit")

    # Save storage state
    context.storage_state(path=str(STORAGE_PATH))
    context.close()

# Verify
with open(STORAGE_PATH) as f:
    data = json.load(f)
names = [c["name"] for c in data["cookies"]]
print(f"\nTotal cookies: {len(names)}")
required = ["SID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID"]
all_ok = True
for r in required:
    status = "OK" if r in names else "MISSING"
    if status == "MISSING":
        all_ok = False
    print(f"  [{status}] {r}")

if all_ok:
    print(f"\n[SUCCESS] Authentication saved to: {STORAGE_PATH}")
else:
    print(f"\n[PARTIAL] Some cookies missing. Saved to: {STORAGE_PATH}")

print("Done!")
