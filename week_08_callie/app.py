import base64
import io
import json
import os
import re
import smtplib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from typing import Any, Optional

import pytz
import requests
import streamlit as st
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from dotenv import load_dotenv
from pydantic import BaseModel
from pypdf import PdfReader

load_dotenv()


class EventRecord(BaseModel):
    title: str
    start: str
    end: str
    description: str = ""
    location: Optional[str] = None


@dataclass
class BackgroundResult:
    filename: str
    ics_bytes: bytes
    event_count: int
    email_sent: bool
    email_message: str
    events: list[dict[str, Any]] = field(default_factory=list)


TIMEZONE_OPTIONS = sorted(pytz.common_timezones)
APP_JOBS: dict[str, object] = {}


def parse_datetime(value: str, timezone_name: str) -> datetime | date:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"

    if len(cleaned) == 10:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()

    parsed = datetime.fromisoformat(cleaned)
    target_tz = pytz.timezone(timezone_name)

    if parsed.tzinfo is None:
        localized = target_tz.localize(parsed, is_dst=None)
        return localized

    return parsed.astimezone(target_tz)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    text_chunks: list[str] = []
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_chunks.append(page_text)
    return "\n\n".join(text_chunks)


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def build_conversion_prompt(source_description: str, current_year: int) -> str:
    return f"""You are a strict calendar extraction engine.
Return ONLY raw JSON with no markdown fences, keys, or explanatory text.
The output must be a JSON array where each object contains:
- title (string)
- start (ISO-8601 string)
- end (ISO-8601 string)
- description (string)
- location (string or null)

Rules:
- Preserve the original event details.
- If the source calendar omits a year, assume {current_year}.
- Use values in the user timezone when possible.
- For each event, append this exact disclaimer note to the description:
  "Disclaimer: This event was generated from an uploaded image/PDF or URL and should be reviewed for accuracy."
- The description field should include the original description text, plus the disclaimer note.
- If there is no original description, still include the disclaimer note in the description.
- If a location is not present, use null.
- If start or end are all-day dates without a time, keep them as YYYY-MM-DD strings.
- If the source contains times, use ISO-8601 values like 2026-07-14T09:00:00 or 2026-07-14T10:00:00.

Source calendar content:
{source_description}
"""


def call_llm(messages: list[dict[str, Any]], max_tokens: int = 2000) -> str:
    api_base = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")

    if not api_base or not api_key or not model:
        raise RuntimeError("Missing OPENAI_API_BASE, OPENAI_API_KEY, or OPENAI_MODEL in environment.")

    response = requests.post(
        f"{api_base.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]["content"]


def generate_ics(events: list[EventRecord], timezone_name: str, recipient_email: str) -> tuple[bytes, str]:
    calendar = Calendar()
    calendar.add("prodid", "-//AI Calendar Converter Prototype//EN")
    calendar.add("version", "2.0")
    calendar.add("x-wr-calname", f"Converted calendar for {recipient_email}")
    calendar.add("x-wr-timezone", timezone_name)

    for event in events:
        ical_event = Event()
        ical_event.add("summary", event.title)
        ical_event.add("description", event.description)
        if event.location:
            ical_event.add("location", event.location)

        start_dt = parse_datetime(event.start, timezone_name)
        end_dt = parse_datetime(event.end, timezone_name)

        ical_event.add("dtstart", start_dt)
        ical_event.add("dtend", end_dt)
        ical_event.add("dtstamp", datetime.now(pytz.utc))
        calendar.add_component(ical_event)

    ics_bytes = calendar.to_ical()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"converted_calendar_{timestamp}.ics"
    return ics_bytes, filename


def send_email_with_ics(recipient_email: str, ics_bytes: bytes, filename: str) -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, smtp_from]):
        return False, "SMTP is not configured; the ICS file is available for local download."

    message = EmailMessage()
    message["Subject"] = "Your converted calendar (.ics)"
    message["From"] = smtp_from
    message["To"] = recipient_email
    message.set_content(
        "Your calendar conversion is ready. The attached .ics file includes the parsed events."
    )
    message.add_attachment(
        ics_bytes,
        maintype="text",
        subtype="calendar",
        filename=filename,
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)

    return True, "Email sent successfully."


def process_calendar_job(
    email: str,
    timezone_name: str,
    source_type: str,
    source_bytes: Optional[bytes],
    url: Optional[str],
    uploaded_file_name: Optional[str] = None,
    uploaded_file_type: Optional[str] = None,
) -> BackgroundResult:
    current_year = datetime.now().year
    source_description = ""

    if source_type == "upload" and source_bytes:
        file_name = (uploaded_file_name or "")
        if file_name.lower().endswith(".pdf"):
            source_description = extract_pdf_text(source_bytes)
            if not source_description.strip():
                raise RuntimeError("PDF text extraction returned no readable text. Try a clearer PDF or upload an image instead.")
        else:
            mime_type = uploaded_file_type or "application/octet-stream"
            encoded = base64.b64encode(source_bytes).decode("utf-8")
            image_data_url = f"data:{mime_type};base64,{encoded}"
            messages = [
                {
                    "role": "system",
                    "content": build_conversion_prompt("Uploaded image content", current_year),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Parse this calendar image into structured JSON events.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url},
                        },
                    ],
                },
            ]
            raw_response = call_llm(messages)
            parsed = json.loads(strip_code_fences(raw_response))
            validated = [EventRecord.model_validate(item) for item in parsed]
            ics_bytes, filename = generate_ics(validated, timezone_name, email)
            email_sent, email_message = send_email_with_ics(email, ics_bytes, filename)
            return BackgroundResult(
                filename=filename,
                ics_bytes=ics_bytes,
                event_count=len(validated),
                email_sent=email_sent,
                email_message=email_message,
                events=[record.model_dump() for record in validated],
            )

    if source_type == "url" and url:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        raw_bytes = response.content
        if content_type.startswith("application/pdf"):
            source_description = extract_pdf_text(raw_bytes)
        elif content_type.startswith("image/"):
            encoded = base64.b64encode(raw_bytes).decode("utf-8")
            mime_type = content_type.split(";", 1)[0].strip()
            image_data_url = f"data:{mime_type};base64,{encoded}"
            messages = [
                {
                    "role": "system",
                    "content": build_conversion_prompt("Uploaded image content", current_year),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Parse this calendar image from the URL into structured JSON events.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url},
                        },
                    ],
                },
            ]
            raw_response = call_llm(messages)
            parsed = json.loads(strip_code_fences(raw_response))
            validated = [EventRecord.model_validate(item) for item in parsed]
            ics_bytes, filename = generate_ics(validated, timezone_name, email)
            email_sent, email_message = send_email_with_ics(email, ics_bytes, filename)
            return BackgroundResult(
                filename=filename,
                ics_bytes=ics_bytes,
                event_count=len(validated),
                email_sent=email_sent,
                email_message=email_message,
                events=[record.model_dump() for record in validated],
            )
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "meta", "head", "nav"]):
                tag.decompose()
            cleaned_text = soup.get_text(separator=" ")
            source_description = re.sub(r"\s+", " ", cleaned_text).strip()

    if not source_description.strip():
        raise RuntimeError("No readable calendar content was found. Upload an image/PDF or provide a URL to a readable calendar resource.")

    prompt = build_conversion_prompt(source_description, current_year)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Parse this calendar content into strict JSON events. The user timezone is {timezone_name}."},
    ]
    raw_response = call_llm(messages)
    parsed = json.loads(strip_code_fences(raw_response))
    validated = [EventRecord.model_validate(item) for item in parsed]

    ics_bytes, filename = generate_ics(validated, timezone_name, email)
    email_sent, email_message = send_email_with_ics(email, ics_bytes, filename)
    return BackgroundResult(
        filename=filename,
        ics_bytes=ics_bytes,
        event_count=len(validated),
        email_sent=email_sent,
        email_message=email_message,
        events=[record.model_dump() for record in validated],
    )


def _run_background_job(
    job_id: str,
    email: str,
    timezone_name: str,
    uploaded_bytes: Optional[bytes],
    source_url: str,
    uploaded_file_name: Optional[str],
    uploaded_file_type: Optional[str],
) -> None:
    try:
        if uploaded_file_name is not None:
            source_type = "upload"
            source_bytes = uploaded_bytes
        elif source_url.strip():
            source_type = "url"
            source_bytes = None
        else:
            raise RuntimeError("No calendar source provided.")

        result = process_calendar_job(
            email=email,
            timezone_name=timezone_name,
            source_type=source_type,
            source_bytes=source_bytes,
            url=source_url.strip() or None,
            uploaded_file_name=uploaded_file_name,
            uploaded_file_type=uploaded_file_type,
        )
        APP_JOBS[job_id] = result
    except Exception as exc:
        APP_JOBS[job_id] = {"status": "error", "error": str(exc)}


st.set_page_config(page_title="AI Calendar Converter", page_icon="📅", layout="wide")

# Initialize states safely
if "processing" not in st.session_state:
    st.session_state.processing = False
if "current_job_id" not in st.session_state:
    st.session_state.current_job_id = None

st.title("AI Calendar Converter Prototype")

if st.session_state.processing:
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(interval=2000, key=f"refresh_{st.session_state.get('current_job_id')}")

st.markdown(
    "Upload a calendar photo or PDF, or point to a URL, then convert the content into an `.ics` file and email the result."
)

with st.container(border=True):
    email = st.text_input("Recipient email (optional)", placeholder="person@example.com")
    st.caption("Leave the email blank to keep the generated `.ics` file available for local download.")
    timezone_name = st.selectbox("Recipient timezone", TIMEZONE_OPTIONS, index=TIMEZONE_OPTIONS.index("UTC"))

    with st.container(border=True):
        source_url = st.text_input("Calendar URL", placeholder="https://example.com/calendar").strip()

    st.markdown(
        "<div style='text-align:center; font-weight:700; margin: 0.5rem 0;'>- OR -</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "Upload photo or PDF",
            type=["png", "jpg", "jpeg", "pdf"],
            accept_multiple_files=False,
        )

    if st.button("Convert calendar", type="primary", disabled=st.session_state.processing):
        source_url = source_url.strip()

        if source_url and not re.match(r"^https?://", source_url):
            st.error("Please enter a valid URL including http:// or https://")
            st.stop()

        if uploaded_file is None and not source_url:
            st.warning("Please upload a file or provide a URL.")
            st.stop()

        job_id = f"calendar_job_{uuid.uuid4().hex}"
        st.session_state.current_job_id = job_id
        st.session_state.processing = True
        st.session_state.processing_started = True

        APP_JOBS[job_id] = {"status": "processing"}

        uploaded_bytes = uploaded_file.getvalue() if uploaded_file is not None else None
        uploaded_file_name = uploaded_file.name if uploaded_file is not None else None
        uploaded_file_type = uploaded_file.type if uploaded_file is not None else None

        thread = threading.Thread(
            target=_run_background_job,
            args=(
                job_id,
                email,
                timezone_name,
                uploaded_bytes,
                source_url,
                uploaded_file_name,
                uploaded_file_type,
            ),
            daemon=True,
        )
        thread.start()

job_id = st.session_state.get("current_job_id")
current_job = APP_JOBS.get(job_id) if job_id else None

if current_job is not None:
    if isinstance(current_job, dict) and current_job.get("status") == "processing":
        with st.spinner("Processing your calendar in the background..."):
            st.info("Analyzing content... check your downloads shortly!")

    elif isinstance(current_job, BackgroundResult):
        result = current_job
        st.session_state.processing = False
        st.session_state.processing_started = False
        st.session_state.current_job_id = None
        st.success("Calendar conversion completed.")
        st.write(f"Parsed {result.event_count} events.")
        st.write(result.email_message)
        st.download_button(
            label="Download generated .ics file",
            data=result.ics_bytes,
            file_name=result.filename,
            mime="text/calendar",
        )
        st.rerun()
    elif isinstance(current_job, dict) and current_job.get("status") == "error":
        st.session_state.processing = False
        st.session_state.processing_started = False
        st.session_state.current_job_id = None
        st.error(current_job.get("error", "An unknown error occurred while processing the calendar."))
        st.rerun()