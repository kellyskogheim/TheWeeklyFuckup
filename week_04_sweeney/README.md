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

Scan for wins
```powershell
uv run win_monitor.py
```

## Enhancements

- users table is not effectively used, eligibility filtering could use an LLM
- tracking winnings needs verification step and ability to manually add if winnings missed by scanner
- switch to the homepage for scraping and add pagination logic.. I think this may only be pulling the first page of each category.. 
- add doc strings
- a million more things that I will likely not do..


