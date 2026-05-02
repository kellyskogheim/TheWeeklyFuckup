# Sweepstakes Fanatics Scraper

This scraper pulls sweepstakes listings from Sweepstakes Fanatics and writes them into `sweeps_tracker.db`.

## Run the scraper

From `c:\Users\Kelly\Documents\git\TheWeeklyFuckup\week_04_sweeney`:

```powershell
uv run python scraper.py
```

If normal requests are blocked, use Playwright:

```powershell
uv run python scraper.py --use-playwright
```

To test without writing to the database:

```powershell
uv run python scraper.py --dry-run
```

## Daily automation

On Windows, schedule this command in Task Scheduler to run once per day:

```powershell
cd "c:\Users\Kelly\Documents\git\TheWeeklyFuckup\week_04_sweeney"
uv run python scraper.py --use-playwright
```

That will keep the `giveaways` table refreshed and mark past end dates as `inactive`.
