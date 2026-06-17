from __future__ import annotations

import argparse
import base64
import html
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# If modifying these scopes, delete token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DB_PATH = "sweeps_tracker.db"
DEFAULT_CREDENTIALS_PATH = "credentials.json"
DEFAULT_TOKEN_PATH = "token.json"

WIN_QUERY = (
    "newer_than:{days}d "
    "("
    "subject:(winner OR won OR congratulations OR congrats OR selected OR finalist OR prize OR claim) "
    "OR "
    "\"you won\" OR \"you are a winner\" OR \"potential winner\" OR \"claim your prize\" "
    "OR \"selected as\" OR \"you're a winner\" OR \"you have won\""
    ")"
)
OFFER_QUERY = (
    "newer_than:{days}d "
    "("
    "subject:(birthday OR reward OR rewards OR free OR bonus OR credit OR certificate OR coupon) "
    "OR "
    "\"birthday reward\" OR \"free reward\" OR \"reward dollars\" OR \"reward money\" "
    "OR \"free item\" OR \"free gift\" OR \"store credit\" OR \"bonus points\""
    ")"
)

WIN_KEYWORDS = {
    "winner": 18,
    "you won": 25,
    "you have won": 25,
    "congratulations": 12,
    "congrats": 10,
    "potential winner": 24,
    "selected as": 14,
    "claim your prize": 28,
    "affidavit": 20,
    "prize fulfillment": 22,
    "tax form": 10,
    "1099": 10,
}
WIN_FALSE_POSITIVES = {
    "enter to win": -18,
    "chance to win": -18,
    "win a": -6,
    "sweepstakes ends": -12,
    "last chance": -10,
    "no purchase necessary": -10,
}
OFFER_KEYWORDS = {
    "birthday reward": 28,
    "birthday gift": 24,
    "free reward": 22,
    "free item": 18,
    "free gift": 18,
    "reward dollars": 26,
    "reward money": 26,
    "store credit": 24,
    "certificate": 14,
    "bonus points": 12,
    "account credit": 24,
    "$5 reward": 18,
    "$10 reward": 22,
    "$15 reward": 24,
    "$20 reward": 26,
    "100% off": 20,
}
OFFER_FALSE_POSITIVES = {
    "free shipping": -14,
    "buy one get one": -8,
    "with purchase": -14,
    "when you spend": -14,
    "limited time": -4,
}


@dataclass
class EmailCandidate:
    gmail_message_id: str
    thread_id: str
    category: str
    subject: str
    sender: str
    received_at: Optional[str]
    snippet: str
    body: str
    score: int
    matched_terms: list[str]


def get_gmail_service():
    credentials_path = os.environ.get("GMAIL_CREDENTIALS_PATH", DEFAULT_CREDENTIALS_PATH)
    token_path = os.environ.get("GMAIL_TOKEN_PATH", DEFAULT_TOKEN_PATH)
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("Token expired or revoked by Google. Re-authenticating...")
                os.remove(token_path)
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        token_dir = os.path.dirname(os.path.abspath(token_path))
        os.makedirs(token_dir, exist_ok=True)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def init_monitor_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_monitor_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_message_id TEXT NOT NULL UNIQUE,
                thread_id TEXT,
                category TEXT NOT NULL,
                subject TEXT,
                sender TEXT,
                received_at DATETIME,
                snippet TEXT,
                score INTEGER NOT NULL,
                matched_terms TEXT,
                review_status TEXT DEFAULT 'new',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promotional_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_hit_id INTEGER NOT NULL,
                offer_type TEXT,
                description TEXT NOT NULL,
                sender TEXT,
                received_at DATETIME,
                status TEXT DEFAULT 'new',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (email_hit_id) REFERENCES email_monitor_hits (id)
            )
            """
        )
        conn.commit()


def decode_body_data(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return ""


def html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(value)


def normalize_text(value: str) -> str:
    value = html_to_text(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def walk_payload_parts(payload: dict) -> Iterable[dict]:
    yield payload
    for part in payload.get("parts", []) or []:
        yield from walk_payload_parts(part)


def extract_message_text(message: dict) -> str:
    text_parts: list[str] = []
    html_parts: list[str] = []
    payload = message.get("payload", {})
    for part in walk_payload_parts(payload):
        body_data = part.get("body", {}).get("data")
        if not body_data:
            continue
        decoded = decode_body_data(body_data)
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain":
            text_parts.append(decoded)
        elif mime_type == "text/html":
            html_parts.append(decoded)

    raw_text = "\n".join(text_parts) if text_parts else "\n".join(html_parts)
    return normalize_text(raw_text)


def get_header(message: dict, name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def internal_date_to_iso(message: dict) -> Optional[str]:
    internal_date = message.get("internalDate")
    if not internal_date:
        return None
    try:
        return datetime.fromtimestamp(int(internal_date) / 1000).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def score_text(text: str, positive_terms: dict[str, int], negative_terms: dict[str, int]) -> tuple[int, list[str]]:
    lower_text = text.lower()
    score = 0
    matched_terms: list[str] = []
    for term, points in positive_terms.items():
        if term in lower_text:
            score += points
            matched_terms.append(term)
    for term, points in negative_terms.items():
        if term in lower_text:
            score += points
            matched_terms.append(f"not:{term}")
    return score, matched_terms


def list_message_ids(service, query: str, max_results: int) -> list[dict]:
    messages: list[dict] = []
    request = service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 100))
    while request is not None and len(messages) < max_results:
        response = request.execute()
        messages.extend(response.get("messages", []))
        if len(messages) >= max_results:
            break
        request = service.users().messages().list_next(request, response)
    return messages[:max_results]


def load_message(service, message_id: str) -> dict:
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()


def build_candidate(service, message_ref: dict, category: str) -> Optional[EmailCandidate]:
    message = load_message(service, message_ref["id"])
    subject = get_header(message, "Subject") or "(no subject)"
    sender = get_header(message, "From")
    snippet = normalize_text(message.get("snippet", ""))
    body = extract_message_text(message)
    scoring_text = " ".join([subject, sender, snippet, body[:5000]])

    if category == "win":
        score, matched_terms = score_text(scoring_text, WIN_KEYWORDS, WIN_FALSE_POSITIVES)
        threshold = 12
    else:
        score, matched_terms = score_text(scoring_text, OFFER_KEYWORDS, OFFER_FALSE_POSITIVES)
        threshold = 14

    if score < threshold:
        return None

    return EmailCandidate(
        gmail_message_id=message["id"],
        thread_id=message.get("threadId", ""),
        category=category,
        subject=subject,
        sender=sender,
        received_at=internal_date_to_iso(message),
        snippet=snippet,
        body=body,
        score=score,
        matched_terms=matched_terms,
    )


def find_matching_giveaway(conn: sqlite3.Connection, candidate: EmailCandidate) -> Optional[tuple[int, str]]:
    text = f"{candidate.subject} {candidate.snippet} {candidate.body[:3000]}".lower()
    rows = conn.execute(
        """
        SELECT DISTINCT g.id, g.name
        FROM giveaways g
        JOIN entries e ON g.id = e.giveaway_id
        ORDER BY LENGTH(g.name) DESC
        """
    ).fetchall()
    for giveaway_id, giveaway_name in rows:
        if giveaway_name and giveaway_name.lower() in text:
            return giveaway_id, giveaway_name
    return None


def insert_email_hit(conn: sqlite3.Connection, candidate: EmailCandidate) -> Optional[int]:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO email_monitor_hits
        (gmail_message_id, thread_id, category, subject, sender, received_at, snippet, score, matched_terms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate.gmail_message_id,
            candidate.thread_id,
            candidate.category,
            candidate.subject,
            candidate.sender,
            candidate.received_at,
            candidate.snippet,
            candidate.score,
            ", ".join(candidate.matched_terms),
        ),
    )
    if cursor.rowcount == 0:
        return None
    return cursor.lastrowid


def log_win_candidate(conn: sqlite3.Connection, candidate: EmailCandidate, email_hit_id: int) -> str:
    match = find_matching_giveaway(conn, candidate)
    if not match:
        return f"Potential win needs review: {candidate.subject}"

    giveaway_id, giveaway_name = match
    prize_description = f"CHECK EMAIL: {candidate.subject}"
    existing = conn.execute(
        "SELECT id FROM winnings WHERE giveaway_id = ? AND prize_description = ?",
        (giveaway_id, prize_description),
    ).fetchone()
    if not existing:
        conn.execute(
            """
            INSERT INTO winnings (giveaway_id, prize_description, date_won, status)
            VALUES (?, ?, DATE('now'), 'unverified')
            """,
            (giveaway_id, prize_description),
        )
    return f"Potential win matched '{giveaway_name}': {candidate.subject}"


def classify_offer_type(candidate: EmailCandidate) -> str:
    text = f"{candidate.subject} {candidate.snippet} {candidate.body[:2000]}".lower()
    if "birthday" in text:
        return "birthday_reward"
    if "reward" in text or "certificate" in text:
        return "reward_credit"
    if "free" in text or "gift" in text:
        return "free_item"
    if "credit" in text:
        return "store_credit"
    return "notable_deal"


def log_offer_candidate(conn: sqlite3.Connection, candidate: EmailCandidate, email_hit_id: int) -> str:
    offer_type = classify_offer_type(candidate)
    description = f"{candidate.subject} | score={candidate.score} | terms={', '.join(candidate.matched_terms)}"
    conn.execute(
        """
        INSERT INTO promotional_opportunities
        (email_hit_id, offer_type, description, sender, received_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (email_hit_id, offer_type, description, candidate.sender, candidate.received_at),
    )
    return f"Promotional opportunity ({offer_type}): {candidate.subject}"


def scan_mail(days: int = 14, max_results: int = 50) -> list[str]:
    init_monitor_db()
    service = get_gmail_service()
    scan_specs = [
        ("win", WIN_QUERY.format(days=days)),
        ("offer", OFFER_QUERY.format(days=days)),
    ]
    summaries: list[str] = []

    with sqlite3.connect(DB_PATH) as conn:
        for category, query in scan_specs:
            for message_ref in list_message_ids(service, query, max_results=max_results):
                candidate = build_candidate(service, message_ref, category)
                if not candidate:
                    continue

                email_hit_id = insert_email_hit(conn, candidate)
                if email_hit_id is None:
                    continue

                if category == "win":
                    summaries.append(log_win_candidate(conn, candidate, email_hit_id))
                else:
                    summaries.append(log_offer_candidate(conn, candidate, email_hit_id))

        conn.commit()

    return summaries


def print_scan_summary(summaries: list[str]) -> None:
    if not summaries:
        print("No new win or promotional-opportunity emails found.")
        return
    print(f"Found {len(summaries)} new email candidate(s):")
    for summary in summaries:
        print(f"- {summary}")


def watch_mail(days: int, max_results: int, interval_minutes: int) -> None:
    print(f"Monitoring Gmail every {interval_minutes} minute(s). Press Ctrl+C to stop.")
    while True:
        print(f"\n[{datetime.now().isoformat(timespec='seconds')}] Scanning...")
        print_scan_summary(scan_mail(days=days, max_results=max_results))
        time.sleep(interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor Gmail for sweepstakes wins and valuable promotional offers.")
    parser.add_argument("--days", type=int, default=14, help="How far back Gmail should search.")
    parser.add_argument("--max-results", type=int, default=50, help="Maximum messages to inspect per category.")
    parser.add_argument("--watch", action="store_true", help="Keep scanning on an interval.")
    parser.add_argument("--interval-minutes", type=int, default=30, help="Watch-mode interval.")
    args = parser.parse_args()

    if args.watch:
        watch_mail(args.days, args.max_results, args.interval_minutes)
    else:
        print_scan_summary(scan_mail(days=args.days, max_results=args.max_results))


if __name__ == "__main__":
    main()
