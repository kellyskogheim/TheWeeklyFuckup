# Sweepstakes Fanatics Scraper and Entry Assitant/Tracker

The scraper pulls sweepstakes listings from Sweepstakes Fanatics and writes them into `sweeps_tracker.db`.
The entry manager opens the active sweepstakes urls that you are eligible for in a Google Chrome window. You can choose to
1) skip this sweepstakes
2) use your preferred auto-fill tool in the browser and complete your entry
3) disregard this sweepstakes 

## Run 

First install uv: https://docs.astral.sh/uv/getting-started/installation

Set-up the python project
```powershell
uv sync
```

Gmail monitoring uses a Google OAuth desktop-app client secret and a local refresh token. Keep both files out of Git. You can either restore `credentials.json` into this folder, or store the files outside the repo and point the script at them:

```powershell
$env:GMAIL_CREDENTIALS_PATH = "$HOME\.config\sweeps-tracker\credentials.json"
$env:GMAIL_TOKEN_PATH = "$HOME\.config\sweeps-tracker\token.json"
uv run win_monitor.py
```

The token grants read access to your Gmail under the scopes in `win_monitor.py`, so treat `token.json` like a password. If it ever leaks, revoke access in your Google Account security settings and delete the local token so the app re-authenticates.

Edit sweeps_tracker_db.py by uncommenting the # Insert your profile section and putting your profile in the Values array
(Only the birth date and state are still used, so you can just enter those only.)

Initialize DB and scrape sweepstakes from sweepstakes fanatics
```powershell
uv run scraper.py
```

Start entering
```powershell
uv run entry_manager.py
```

Scan Gmail for sweepstakes wins and unusually valuable promotional offers
```powershell
uv run win_monitor.py --days 14
```

Keep the monitor running while your computer is on
```powershell
uv run win_monitor.py --watch --interval-minutes 30
```

The monitor writes likely win emails to `email_monitor_hits` and, when it can match the email to a giveaway you entered, adds an unverified row to `winnings`. It writes birthday rewards, reward credits, free items, store credits, and similar high-value promotional emails to `promotional_opportunities`.

Review newly detected email opportunities
```powershell
sqlite3 sweeps_tracker.db "SELECT id, category, subject, sender, score, matched_terms FROM email_monitor_hits WHERE review_status = 'new' ORDER BY received_at DESC;"
sqlite3 sweeps_tracker.db "SELECT id, offer_type, description, sender, status FROM promotional_opportunities WHERE status = 'new' ORDER BY received_at DESC;"
```

## Enhancements

- users table is not effectively used, eligibility filtering could use an LLM
- tracking winnings needs verification step and ability to manually add if winnings missed by scanner
- switch to the homepage for scraping and add pagination logic.. I think this may only be pulling the first page of each category.. 
- add doc strings
- a million more things that I will likely not do..


