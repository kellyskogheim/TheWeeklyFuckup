from __future__ import annotations

import argparse
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from sweeps_tracker_db import init_db


BASE_URL = "https://sweepstakesfanatics.com"
CATEGORIES_URL = urljoin(BASE_URL, "/categories/")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}
REQUEST_DELAY_SECONDS = 1.0

INACTIVE_PATTERNS = [
    r"\bclosed\b",
    r"\bexpired\b",
    r"\bno longer available\b",
    r"\bwinners? have been selected\b",
    r"\bwinner(s)? selected\b",
    r"\bdrawing complete\b",
    r"\bdrawing has occurred\b",
]

CATEGORY_URL_PATTERN = re.compile(r"/[A-Za-z0-9-]+-sweepstakes/?$", re.I)


@dataclass
class SweepstakesItem:
    name: str
    entry_url: str
    frequency: Optional[str] = None
    eligibility: Optional[str] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    rules_url: Optional[str] = None
    status: str = "pending"


def get_soup(url: str, use_playwright: bool = False) -> BeautifulSoup:
    if use_playwright and PLAYWRIGHT_AVAILABLE:
        return _get_soup_via_playwright(url)

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _get_soup_via_playwright(url: str) -> BeautifulSoup:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], java_script_enabled=True)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        html = page.content()
        browser.close()
    return BeautifulSoup(html, "html.parser")


def is_category_url(href: str, text: str) -> bool:
    if not href:
        return False
    normalized_href = href.strip()
    if normalized_href.startswith("/"):
        normalized_href = urljoin(BASE_URL, normalized_href)
    if not normalized_href.startswith(BASE_URL):
        return False
    if CATEGORY_URL_PATTERN.search(normalized_href) and "sweepstakes" in text.lower():
        return True
    return False


def extract_category_urls(soup: BeautifulSoup) -> List[str]:
    urls: List[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor["href"].strip()
        text = anchor.get_text(separator=" ", strip=True)
        if is_category_url(href, text):
            full_url = urljoin(BASE_URL, href)
            if full_url not in urls:
                urls.append(full_url)
    return urls


def extract_sweepstakes_from_category(soup: BeautifulSoup, category_name: str) -> List[SweepstakesItem]:
    results: List[SweepstakesItem] = []
    for card in soup.select("div.col-sm-6"):
        title_el = card.select_one("h2.post-title a")
        more_link = card.select_one("div.entry.basic-1.clearfix a.more-link")
        if not title_el or not more_link:
            continue
        name = title_el.get_text(strip=True)
        entry_url = urljoin(BASE_URL, title_el["href"].strip())
        results.append(SweepstakesItem(name=name, entry_url=entry_url))
    return results


def clean_text(text: str) -> str:
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def parse_date(date_str: str) -> Optional[datetime.date]:
    try:
        return datetime.strptime(date_str, "%B %d, %Y").date()
    except ValueError:
        return None


def parse_date_label(label: str, text: str) -> Optional[str]:
    pattern = re.compile(rf"{re.escape(label)}:\s*([A-Za-z]+ \d{{1,2}}, \d{{4}})", re.I)
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def parse_eligibility(text: str) -> Optional[str]:
    match = re.search(r"Eligibility:\s*(.+?)(?:\n|$)", text, re.I)
    return match.group(1).strip() if match else None


def parse_frequency(text: str) -> Optional[str]:
    match = re.search(r"Entry Frequency:\s*(.+?)(?:\n|$)", text, re.I)
    return match.group(1).strip() if match else None


def parse_status(text: str) -> str:
    lower_text = text.lower()
    for pattern in INACTIVE_PATTERNS:
        if re.search(pattern, lower_text):
            return "inactive"
    return "active"


def extract_detail_data(url: str, use_playwright: bool = False) -> dict:
    soup = get_soup(url, use_playwright=use_playwright)
    content_block = soup.select_one("div.content-detail") or soup.select_one("div.entry-content") or soup.select_one("section.content")
    page_text = clean_text(content_block.get_text(separator=" \n", strip=True) if content_block else soup.get_text(separator=" \n", strip=True))

    return {
        "status": parse_status(page_text),
        "eligibility": parse_eligibility(page_text),
        "frequency": parse_frequency(page_text),
        "start_date": parse_date(parse_date_label("Start Date", page_text) or ""),
        "end_date": parse_date(parse_date_label("End Date", page_text) or ""),
        "rules_url": next((anchor["href"] for anchor in soup.select("a[href]") if "rules" in anchor.get_text(strip=True).lower()), None),
    }


def save_giveaway(conn: sqlite3.Connection, item: SweepstakesItem, dry_run: bool = False) -> None:
    if dry_run:
        print(f"  Dry run: would save {item.name} ({item.status}) ends {item.end_date}")
        return

    conn.execute(
        """
        INSERT INTO giveaways
        (name, entry_url, frequency, eligibility, start_date, end_date, rules_url, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entry_url, start_date) DO UPDATE SET
            frequency=excluded.frequency,
            eligibility=excluded.eligibility,
            end_date=excluded.end_date,
            rules_url=excluded.rules_url,
            status=excluded.status
        """,
        (
            item.name,
            item.entry_url,
            item.frequency,
            item.eligibility,
            item.start_date,
            item.end_date,
            item.rules_url,
            item.status,
        ),
    )
    conn.commit()


def has_entry_history(conn: sqlite3.Connection, entry_url: str, start_date: Optional[datetime.date]) -> bool:
    if start_date is None:
        return False

    cursor = conn.execute(
        "SELECT 1 FROM entries e JOIN giveaways g ON e.giveaway_id = g.id WHERE g.entry_url = ? AND g.start_date = ? LIMIT 1",
        (entry_url, start_date),
    )
    return cursor.fetchone() is not None


def run_scraper(use_playwright: bool = False, dry_run: bool = False) -> None:
    init_db()
    today = datetime.now().date()
    categories_soup = get_soup(CATEGORIES_URL, use_playwright=use_playwright)
    category_urls = extract_category_urls(categories_soup)

    with sqlite3.connect("sweeps_tracker.db") as conn:
        seen_urls: set[str] = set()
        for category_url in category_urls:
            category_name = category_url.rstrip("/").split("/")[-1].replace("-sweepstakes", "").replace("-", " ").title()
            print(f"Processing category: {category_name} -> {category_url}")
            page_soup = get_soup(category_url, use_playwright=use_playwright)
            items = extract_sweepstakes_from_category(page_soup, category_name)

            for item in items:
                if item.entry_url in seen_urls:
                    continue
                seen_urls.add(item.entry_url)

                detail_data = extract_detail_data(item.entry_url, use_playwright=use_playwright)
                item.status = detail_data["status"]
                item.eligibility = detail_data["eligibility"]
                item.frequency = detail_data["frequency"]
                item.start_date = detail_data["start_date"]
                item.end_date = detail_data["end_date"]
                item.rules_url = detail_data["rules_url"]

                if item.end_date and item.end_date < today:
                    item.status = "inactive"

                if has_entry_history(conn, item.entry_url, item.start_date):
                    print(f"  Skipping because entry history exists: {item.name}")
                    continue

                save_giveaway(conn, item, dry_run=dry_run)
                if not dry_run:
                    print(f"  Saved: {item.name} ({item.status}) ends {item.end_date}")
                time.sleep(REQUEST_DELAY_SECONDS)

            time.sleep(REQUEST_DELAY_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Sweepstakes Fanatics sweepstakes and populate giveaways.")
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Use Playwright to fetch pages when requests alone is blocked.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the scraper without writing updates to the database.",
    )
    args = parser.parse_args()
    if args.use_playwright and not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright is not installed. Install it or omit --use-playwright.")
    run_scraper(use_playwright=args.use_playwright, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
