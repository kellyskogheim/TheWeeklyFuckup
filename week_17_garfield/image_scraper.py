import argparse
import base64
import re
from datetime import datetime
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROJECT_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = PROJECT_DIR / "credentials.json"
TOKEN_PATH = PROJECT_DIR / "token.json"
GARDEN_DIR = PROJECT_DIR / "garden"


def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("Token expired or revoked. Re-authenticating...")
                TOKEN_PATH.unlink(missing_ok=True)
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def iter_parts(part):
    """Yield every MIME part, including parts nested inside multipart messages."""
    yield part
    for child in part.get("parts", []):
        yield from iter_parts(child)


def safe_name(value, fallback="garden-photo"):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_").lower()
    return cleaned[:60] or fallback


def build_query(after=None, before=None, extra_query=None):
    # from:me matches messages sent by the authenticated Gmail account.
    terms = ["from:me", "has:attachment"]
    if after:
        terms.append(f"after:{after}")
    if before:
        terms.append(f"before:{before}")
    if extra_query:
        terms.append(f"({extra_query})")
    return " ".join(terms)


def list_matching_messages(service, query):
    messages = []
    page_token = None
    while True:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        messages.extend(response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return messages


def scrape_garden_images(after=None, before=None, extra_query=None, dry_run=False):
    service = get_gmail_service()
    query = build_query(after, before, extra_query)
    print(f"Gmail query: {query}")

    messages = list_matching_messages(service, query)
    if not messages:
        print("No matching messages with attachments were found.")
        return

    GARDEN_DIR.mkdir(exist_ok=True)
    saved = skipped = candidates = 0

    for summary in messages:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=summary["id"], format="full")
            .execute()
        )
        headers = {
            header["name"].lower(): header["value"]
            for header in message["payload"].get("headers", [])
        }
        subject = safe_name(headers.get("subject", "garden-photo"))
        sent_at = datetime.fromtimestamp(int(message["internalDate"]) / 1000)
        date_prefix = sent_at.strftime("%Y-%m-%d_%H%M%S")
        message_key = message["id"][:8]

        image_parts = [
            part
            for part in iter_parts(message["payload"])
            if part.get("filename")
            and part.get("mimeType", "").lower().startswith("image/")
            and part.get("body", {}).get("attachmentId")
        ]

        for index, part in enumerate(image_parts, start=1):
            candidates += 1
            extension = Path(part["filename"]).suffix.lower() or ".img"
            filename = (
                f"{date_prefix}_{subject}_{message_key}_{index:02d}{extension}"
            )
            destination = GARDEN_DIR / filename

            if destination.exists():
                print(f"Already imported: {destination.name}")
                skipped += 1
                continue
            if dry_run:
                print(f"Would save: {destination.name}")
                continue

            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(
                    userId="me",
                    messageId=message["id"],
                    id=part["body"]["attachmentId"],
                )
                .execute()
            )
            destination.write_bytes(base64.urlsafe_b64decode(attachment["data"]))
            print(f"Saved: {destination.name}")
            saved += 1

    print(
        f"Finished: {candidates} image(s) matched, "
        f"{saved} saved, {skipped} already present."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download image attachments from Gmail messages sent by you."
    )
    parser.add_argument(
        "--after",
        help="Only messages after this date, using Gmail format YYYY/MM/DD.",
    )
    parser.add_argument(
        "--before",
        help="Only messages before this date, using Gmail format YYYY/MM/DD.",
    )
    parser.add_argument(
        "--query",
        help="Optional additional Gmail search terms, such as 'subject:garden'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching image filenames without downloading them.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    scrape_garden_images(
        after=args.after,
        before=args.before,
        extra_query=args.query,
        dry_run=args.dry_run,
    )
