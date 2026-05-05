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

## Enhancements

- playwright dependency is likely not needed and can be removed from scraper
- users table is not effectively used, eligibility filtering could use an LLM
- tracking winnings is not in here yet.. I haven't won anything.. should monitor sweepstakes email and add
- switch to the homepage for scraping and add pagination logic.. I think this may only be pulling the first page of each category.. 
- add doc strings
- a million more things that I will likely not do..


