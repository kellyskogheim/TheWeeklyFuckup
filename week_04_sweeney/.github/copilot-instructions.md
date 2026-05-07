# Sweepstakes Assistant Project Rules

## Project Goal
A sweepstakes entry and tracking system.
- Source: sweepstakesfanatics.com
- Tech Stack: Python 3.14, SQLite, BeautifulSoup

## Coding Standards
- Use `uv` for package management.
- Always include type hints in Python functions.

## Database Context
- Master DB: sweeps_tracker.db
- Use separate tables for `giveaways`, `entries`, and `winnings` to allow for tax reporting and daily entry tracking.