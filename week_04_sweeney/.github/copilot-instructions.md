# Sweepstakes Assistant Project Rules

## Project Goal
A sweepstakes entry and tracking system.
- Source: sweepstakesfanatics.com
- User State: Michigan
- Tech Stack: Python 3.14, SQLite, BeautifulSoup, Playwright (Stealth mode)

## Coding Standards
- Use `uv` for package management.
- Always include type hints in Python functions.
- Use a "human-in-the-loop" philosophy for automation (don't fully automate CAPTCHAs).

## Database Context
- Master DB: sweeps_tracker.db
- Use separate tables for `giveaways`, `entries`, and `winnings` to allow for tax reporting and daily entry tracking.