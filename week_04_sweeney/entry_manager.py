from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Dict, List

from playwright.sync_api import sync_playwright

from sweeps_tracker_db import get_active_user, get_eligible_giveaways, record_entry


def wait_for_form_submission(prompt: str) -> bool:
    """
    Wait for user input. Return False if ESC pressed (Windows), True if Enter pressed.
    """
    if sys.platform == 'win32':
        import msvcrt
        print(f"{prompt} (Press Enter to continue or ESC to skip)")
        while True:
            key = msvcrt.getch()
            if key == b'\r':  # Enter key
                return True
            elif key == b'\x1b':  # ESC key
                return False
    else:
        # Fallback for non-Windows: just use input()
        response = input(prompt + " (Press Enter to continue or 'esc' then Enter to skip)\n").strip().lower()
        return response != 'esc'


def autofill_form(page, user: Dict[str, str]) -> None:
    # Common field selectors - adjust based on actual forms
    field_mappings = {
        'input[name="first_name"], input[name="firstname"], input[placeholder*="first name" i]': user.get('first_name', ''),
        'input[name="last_name"], input[name="lastname"], input[placeholder*="last name" i]': user.get('last_name', ''),
        'input[name="email"], input[type="email"], input[placeholder*="email" i]': user.get('email', ''),
        'input[name="state"], select[name="state"], input[placeholder*="state" i]': user.get('state_code', ''),
        'input[name="zip"], input[name="zipcode"], input[placeholder*="zip" i]': user.get('zip_code', ''),
        'input[name="phone"], input[name="phone_number"], input[placeholder*="phone" i]': user.get('phone_number', ''),
        'input[name="address"], input[placeholder*="address" i]': user.get('address', ''),
        'input[name="city"], input[placeholder*="city" i]': user.get('city', ''),
        'input[name="country"], select[name="country"], input[placeholder*="country" i]': user.get('country', ''),
    }
    
    for selector, value in field_mappings.items():
        if value:
            try:
                elements = page.query_selector_all(selector)
                for element in elements:
                    element.fill(value)
            except Exception as e:
                print(f"Could not fill {selector}: {e}")


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
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)  # Visible browser
        context = browser.new_context()
        
        for idx, giveaway in enumerate(giveaways, 1):
            print(f"\n[{idx}/{len(giveaways)}] Processing: {giveaway['name']}")
            page = context.new_page()
            page.goto(giveaway['entry_url'], wait_until="domcontentloaded", timeout=60000)
            
            # Autofill the form
            autofill_form(page, user)
            
            # Wait for human interaction (Enter to continue, ESC to skip)
            prompt = f"Complete the form for {giveaway['name']} and"
            should_record = wait_for_form_submission(prompt)
            
            if should_record:
                # Record the entry
                record_entry(giveaway['id'], datetime.now())
                print(f"✓ Recorded entry for {giveaway['name']}")
            else:
                print(f"⊘ Skipped entry for {giveaway['name']}")
            
            page.close()
            time.sleep(2)  # Brief pause between entries
        
        browser.close()
        print("\nAll entries processed.")


if __name__ == "__main__":
    run_entry_manager()