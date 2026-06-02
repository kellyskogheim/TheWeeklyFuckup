import io
import base64
import streamlit as st
import pytz
import os
import re
import pandas as pd
from icalendar import Calendar, Event
from datetime import datetime, date, timedelta
try:
	from dateutil.parser import parse as parse_date
except Exception:
	def parse_date(s):
		# best-effort fallback
		try:
			return datetime.fromisoformat(s)
		except Exception:
			try:
				return datetime.strptime(s, "%Y-%m-%d")
			except Exception:
				return s

from pypdf import PdfReader
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


st.set_page_config(page_title="Smart Calendar Converter", layout="wide")


class EventRecord(BaseModel):
	title: str = Field(description="The name of the calendar event")
	start: str = Field(description="The ISO 8601 string or YYYY-MM-DD representing the start date/time")
	end: str = Field(description="The ISO 8601 string or YYYY-MM-DD representing the end date/time")
	description: str = Field(default="", description="Additional details or notes about the event")
	location: str = Field(default="", description="Where the event takes place, if specified")


class CalendarExtraction(BaseModel):
	events: list[EventRecord]


def extract_pdf_text(uploaded_file) -> str:
	"""Extract text from an uploaded PDF (Streamlit UploadedFile).

	Returns the concatenated text of all pages.
	"""
	if uploaded_file is None:
		return ""

	pdf_bytes = uploaded_file.getvalue()
	if not pdf_bytes:
		return ""

	reader = PdfReader(io.BytesIO(pdf_bytes))
	parts = []
	for page in reader.pages:
		try:
			text = page.extract_text() or ""
		except Exception:
			text = ""
		parts.append(text)
	return "\n\n".join(parts)


def generate_ics(events: list[dict]) -> bytes:
	cal = Calendar()
	cal.add('prodid', '-//Smart Calendar Converter//')
	cal.add('version', '2.0')

	for ev in events:
		e = Event()
		title = ev.get('title') or ev.get('summary') or 'Event'
		e.add('summary', title)
		if ev.get('description'):
			e.add('description', ev.get('description'))
		if ev.get('location'):
			e.add('location', ev.get('location'))

		start_raw = ev.get('start')
		end_raw = ev.get('end') or start_raw

		# Determine if inputs are date-only (YYYY-MM-DD)
		def is_date_only(s):
			return isinstance(s, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', s)

		start_dt = None
		end_dt = None
		is_all_day = False

		if start_raw and is_date_only(start_raw):
			# start provided as date only -> all-day
			try:
				start_dt = datetime.strptime(start_raw, "%Y-%m-%d").date()
				is_all_day = True
			except Exception:
				start_dt = None
		else:
			try:
				start_dt = parse_date(start_raw) if start_raw else None
			except Exception:
				start_dt = None

		if end_raw and is_date_only(end_raw):
			try:
				end_dt = datetime.strptime(end_raw, "%Y-%m-%d").date()
				is_all_day = True
			except Exception:
				end_dt = None
		else:
			try:
				end_dt = parse_date(end_raw) if end_raw else None
			except Exception:
				end_dt = None

		# If times indicate full-day (00:00 -> 23:59:59), treat as all-day
		if not is_all_day and isinstance(start_dt, datetime) and isinstance(end_dt, datetime):
			if start_dt.time() == datetime.min.time() and end_dt.time() == datetime.max.time().replace(microsecond=0):
				is_all_day = True

		if is_all_day:
			# For all-day events, use date values and make dtend exclusive (end + 1 day)
			if isinstance(start_dt, datetime):
				start_date = start_dt.date()
			else:
				start_date = start_dt

			if isinstance(end_dt, datetime):
				end_date = end_dt.date()
			else:
				end_date = end_dt or start_date

			if start_date:
				e.add('dtstart', start_date)
				# dtend for all-day should be the day after the last full day
				try:
					cal_end = (end_date + timedelta(days=1)) if end_date else (start_date + timedelta(days=1))
					e.add('dtend', cal_end)
				except Exception:
					pass
			else:
				# fallback to no dates
				pass
		else:
			# Timed events: use datetime objects directly
			if isinstance(start_dt, (datetime, date)):
				e.add('dtstart', start_dt)
			if isinstance(end_dt, (datetime, date)) and end_dt != start_dt:
				e.add('dtend', end_dt)
		try:
			start_dt = parse_date(start_raw) if start_raw else None
		except Exception:
			start_dt = None
		try:
			end_dt = parse_date(end_raw) if end_raw else None
		except Exception:
			end_dt = None

		if isinstance(start_dt, (datetime, date)):
			e.add('dtstart', start_dt)
		if isinstance(end_dt, (datetime, date)) and end_dt != start_dt:
			e.add('dtend', end_dt)

		cal.add_component(e)

	return cal.to_ical()


def render():
	if "extracted_json" not in st.session_state:
		st.session_state.extracted_json = None

	col1, col2 = st.columns([1, 1])

	# Left column: controls
	with col1:
		st.title("📅 Smart Calendar Converter")

		tz_default = "UTC"
		try:
			tz_index = list(pytz.common_timezones).index(tz_default)
		except ValueError:
			tz_index = 0

		timezone = st.selectbox("Select timezone", pytz.common_timezones, index=tz_index)

		uploaded_pdf = st.file_uploader("Upload calendar PDF", type=["pdf"], accept_multiple_files=False)

		process_disabled = uploaded_pdf is None
		clicked = st.button("Process Calendar", disabled=process_disabled)

		# Handle processing on click
		if clicked and uploaded_pdf is not None:
			with st.spinner("Extracting calendar text and consulting the LLM via LangChain..."):
				extracted_text = extract_pdf_text(uploaded_pdf)

				# Initialize the LLM and bind structured output
				llm = ChatGroq(
					temperature=0,
					model_name=os.getenv("OPENAI_MODEL"),
					groq_api_key=os.getenv("OPENAI_API_KEY"),
					max_tokens=4000,
				)
				structured_llm = llm.with_structured_output(CalendarExtraction)

				# Build a simple prompt text
				system_instructions = (
					"You are a calendar extraction assistant. Parse the provided document text into a list of events. "
					"Return only the structured JSON matching the CalendarExtraction model. "
					"If an event omits a year, assume the year is the current year (2026)."
				)

				prompt_text = (
					f"{system_instructions}\n\nDocument text:\n{extracted_text}\n\nTimezone: {timezone}"
				)

				# Invoke the structured LLM with a single string prompt (Chat models expect str/PromptValue/list)
				try:
					result = structured_llm.invoke(prompt_text)
				except Exception as e:
					st.error(f"LLM invocation failed: {e}")
					result = None

				# Store the structured Pydantic output in session state
				if result is not None:
					try:
						st.session_state.extracted_json = result.model_dump()
					except Exception:
						# Fallback: if result is already a dict-like
						st.session_state.extracted_json = getattr(result, "data", None) or result

		# Success indicator, interactive editor, and ICS generation
		if st.session_state.extracted_json:
			st.success("Calendar context successfully extracted!")
			# Prepare events list for editing
			events = None
			if isinstance(st.session_state.extracted_json, dict):
				events = st.session_state.extracted_json.get('events') or []
			elif isinstance(st.session_state.extracted_json, list):
				events = st.session_state.extracted_json
			else:
				events = []

			# Show editable table
			try:
				df = pd.DataFrame(events)
			except Exception:
				df = pd.DataFrame()

			if not df.empty:
				edited_df = st.data_editor(df, num_rows="dynamic")
				# persist edits back to session state
				if edited_df is not None:
					st.session_state.extracted_json['events'] = edited_df.to_dict(orient='records')
			else:
				st.info("No events found in extracted data to edit.")

			st.markdown("---")
			if st.button("Generate .ics and Download"):
				events_for_ics = st.session_state.extracted_json.get('events') if isinstance(st.session_state.extracted_json, dict) else st.session_state.extracted_json
				ics_bytes = generate_ics(events_for_ics or [])
				if ics_bytes:
					st.download_button(label="Download .ics", data=ics_bytes, file_name="calendar.ics", mime="text/calendar", key="download_ics")

	# Right column: preview
	with col2:
		st.header("📄 Document Preview")

		if uploaded_pdf is not None:
			pdf_bytes = uploaded_pdf.getvalue()
			if pdf_bytes:
				b64 = base64.b64encode(pdf_bytes).decode("ascii")
				iframe_html = f"<iframe src=\"data:application/pdf;base64,{b64}\" width=\"100%\" height=\"700px\"></iframe>"
				st.markdown(iframe_html, unsafe_allow_html=True)
			else:
				st.info("Uploaded file is empty or could not be read.")
		else:
			st.info("Upload a calendar PDF on the left to see a live document preview here.")


if __name__ == "__main__":
	render()

