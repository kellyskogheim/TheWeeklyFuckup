# AI Calendar Converter Prototype

This prototype uses Streamlit to accept a timezone and calendar PDF upload, then parses the calendar content with an OpenAI-compatible vision/text LLM, and generates an `.ics` file.

## Setup

1. Install dependencies:
   `uv sync`

2. Populate `.env` with:
   - `OPENAI_API_BASE`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`

3. Run the app:
   `uv run --env-file .env streamlit run app.py`


