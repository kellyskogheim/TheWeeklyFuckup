# Garfield Garden Assistant

Garfield is a local gardening and yard-management assistant. Yard photographs live
in `garden/`; goals, source code, and the SQLite database live at the project root.

## Importing garden images from Gmail

The scraper reads image attachments from messages sent by the authenticated Gmail
account and saves them directly in `garden/`. It has read-only Gmail access and
does not modify messages.

### First-time setup

1. Enable the Gmail API in the Google Cloud project.
2. Create an OAuth 2.0 **Desktop app** client.
3. Download its JSON file to the project root as `credentials.json`.
4. Install the project dependencies:

   ```powershell
   uv sync
   ```

`credentials.json` and the generated `token.json` are ignored by Git. On the first
run, a browser opens so the Google account can authorize read-only Gmail access.

### Preview an import

Use `--dry-run` to see which image files would be created without downloading
them:

```powershell
uv run python image_scraper.py --after 2026/08/09 --before 2026/08/12 --dry-run
```

The generated Gmail query always includes `from:me has:attachment`. `from:me`
means the message was sent by the authenticated Gmail account, including a message
sent to that same account.

### Download images

Run the same command without `--dry-run`:

```powershell
uv run python image_scraper.py --after 2026/08/09 --before 2026/08/12
```

Dates use `YYYY/MM/DD`. `--after` and `--before` are optional. An additional Gmail
search can narrow the results:

```powershell
uv run python image_scraper.py --after 2026/08/14 --query "subject:garden"
```

The scraper supports nested attachments and multiple images per message. Filenames
include the message date and a stable message identifier, so repeating an import
skips images that are already present.

See every option with:

```powershell
uv run python image_scraper.py --help
```

## Yard database

The local SQLite database tracks zones, condition observations, overhaul projects,
recurring maintenance, and scheduled work sessions. It intentionally does not
track individual plants yet.

Create or update the database and seed the known zones:

```powershell
uv run python garden_db.py init
```

Initialization also creates one high-priority umbrella project for each known
overhaul zone: F2, G2, G3, G4, and S1. Repeating `init` does not duplicate them.

Show a yard overview:

```powershell
uv run python garden_db.py summary
```

Add a condition observation:

```powershell
uv run python garden_db.py observe F2 "Dense poison ivy near the driveway" --severity 5 --image "2026-08-10_144035_overgrown-poison-ivy-ridden-garden-front-west-yard_19fecfa0_01.jpeg"
```

Add maintenance work:

```powershell
uv run python garden_db.py add-maintenance B1 "Trim ivy behind rocks" --minutes 45 --recurrence "every 4 weeks, April-October"
```

Add a manageable project step and schedule a work session:

```powershell
uv run python garden_db.py add-project F2 "Clear first section safely" --priority high
uv run python garden_db.py schedule F2 "Clear first F2 section" "2026-08-22 09:00" "2026-08-22 10:30" --project-id 1
```

The generated `garden.db` is ignored by Git. The schema and initial zone list are
kept in `garden_db.py`, so a fresh database can always be recreated.

### Image-to-zone mapping

Register the files currently in `garden/` and apply the visually reviewed zone
mappings:

```powershell
uv run python garden_db.py sync-images
```

Review the result:

```powershell
uv run python garden_db.py image-map
```

An image can belong to multiple zones. `*` identifies its primary zone, and each
mapping carries a high, medium, or low confidence. The bird's-eye view is stored as
a reference image without assigning it to a single zone.

Correct or add a mapping using the exact filename shown by `image-map`:

```powershell
uv run python garden_db.py map-image "photo-filename.jpeg" G2 --primary --confidence high --notes "Confirmed from garage landmarks"
```

Making a mapping primary clears the previous primary designation but preserves its
secondary relationship. Later image syncs do not overwrite manual corrections.
