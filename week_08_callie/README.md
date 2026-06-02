# AI Calendar Converter Prototype

This prototype uses Streamlit to accept an email recipient, timezone, calendar image/PDF upload, or URL, then parses the calendar content with an OpenAI-compatible vision/text LLM, generates an `.ics` file, and optionally emails it.

## Setup

1. Install dependencies:
   `uv sync`

2. Populate `.env` with:
   - `OPENAI_API_BASE`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - SMTP variables for email delivery

3. Run the app:
   `streamlit run app.py`

## Notes

- The UI immediately shows a background-processing message when the conversion starts.
- Completed conversions expose a local `.ics` download fallback.
- Event descriptions include the required review disclaimer.
