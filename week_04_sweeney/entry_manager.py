from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List

from helpers import get_active_user, get_eligible_giveaways, record_entry, update_giveaway_status


def wait_for_form_submission(prompt: str) -> str:
    """
    Wait for user input. Return 'record' for Enter, 'skip' for ESC, or 'disregard' for 'd'.
    """
    if sys.platform == 'win32':
        import msvcrt
        print(f"{prompt} (Press Enter to record, ESC to skip, or 'd' to disregard)")
        while True:
            key = msvcrt.getch()
            if key == b'\r':  # Enter key
                return 'record'
            elif key == b'\x1b':  # ESC key
                return 'skip'
            elif key.lower() == b'd':  # 'd' key
                return 'disregard'
    else:
        response = input(prompt + " (Press Enter to record, 'esc' to skip, or 'd' to disregard)\n").strip().lower()
        if response == 'd':
            return 'disregard'
        return 'skip' if response == 'esc' else 'record'


def open_url_in_chrome(url: str) -> None:
    """Open the URL in Google Chrome if available, otherwise in the system default browser."""
    if sys.platform == 'win32':
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for chrome_path in chrome_paths:
            if os.path.exists(chrome_path):
                subprocess.Popen([chrome_path, "--new-window", url], close_fds=True)
                return

        try:
            subprocess.Popen(["chrome", "--new-window", url], close_fds=True)
            return
        except OSError:
            pass

        subprocess.Popen(["cmd", "/c", "start", "", url], shell=True)
        return

    if sys.platform == 'darwin':
        subprocess.Popen(["open", "-a", "Google Chrome", url], close_fds=True)
        return

    try:
        subprocess.Popen(["google-chrome", "--new-window", url], close_fds=True)
    except OSError:
        try:
            subprocess.Popen(["chrome", "--new-window", url], close_fds=True)
        except OSError:
            import webbrowser
            webbrowser.open_new(url)


def run_entry_manager() -> None:
    user = get_active_user()
    if not user:
        print("No active user found. Please set an active user in the database.")
        return
    
    giveaways = get_eligible_giveaways()
    if not giveaways:
        print("No eligible giveaways found.")
        return
    
    print(f"Found {len(giveaways)} eligible giveaways for user {user['first_name']} {user['last_name']}.")
    print(f"Will process {len(giveaways)} entries.\n")

    for idx, giveaway in enumerate(giveaways, 1):
        print(f"\n[{idx}/{len(giveaways)}] Opening: {giveaway['name']}")
        print(f"URL: {giveaway['entry_url']}")
        print(f"Frequency: {giveaway['frequency']}")
        print(f"Eligibility: {giveaway['eligibility']}")
        open_url_in_chrome(giveaway['entry_url'])

        prompt = f"Complete the form for {giveaway['name']} and"
        action = wait_for_form_submission(prompt)

        if action == 'record':
            record_entry(giveaway['id'], datetime.now())
            print(f"✓ Recorded entry for {giveaway['name']}")
        elif action == 'disregard':
            update_giveaway_status(giveaway['id'], 'disregarded')
            print(f"🚫 Marked as disregarded: {giveaway['name']}")
        else:  # skip
            print(f"⊘ Skipped entry for {giveaway['name']}")
        time.sleep(2)

    print("\nAll entries processed.")


if __name__ == "__main__":
    run_entry_manager()