# CAS CE Agent

A local-first continuing education tracker modeled on the CAS
`2023-Actuary-CE-Attestation-spreadsheet-no-identifying-information.xlsx`
template. It stores calendar activity in SQLite, keeps planned events separate from
completed credit, checks progress against the 2021 U.S. Qualification Standards
(USQS), monitors official policy/event sources, and exports an audit-ready workbook.

This tool assists with recordkeeping and review. It does not decide whether an
activity qualifies; the actuary remains responsible for that judgment.

## Current rule profile

The default general USQS profile tracks:

- 30 total CE hours, where 50 minutes equals one CE hour
- at least 6 hours of organized activity
- at least 3 hours of professionalism
- at least 1 hour on bias topics
- no more than 3 general-business hours counted toward the total

With `--specific`, it also tracks the template's section 3.3 targets: 15 specific
hours and 6 specific organized hours. Professionalism or bias time can also count
as organized when the same activity independently meets both definitions.

Official sources:

- USQS: https://www.actuary.org/sites/default/files/2021-11/USQS_2021.pdf
- USQS FAQs: https://actuary.org/professionalism/us-qualification-standards/u-s-qualification-standards-faqs/
- CAS CE FAQs: https://www.casact.org/sites/default/files/2025-10/2025_CAS_CE_Policy_FAQs.pdf

## Start locally

```powershell
uv sync
uv run ce-agent init
uv run ce-agent status --year 2026
```

The default database is `data/ce.sqlite3`, which is ignored by Git.

## Connect the "Actuarial CE" Google Calendar

This Codex session does not currently have a Google Calendar connector. The local
app supports Google's read-only Calendar API:

1. In Google Cloud, enable the Google Calendar API and create an OAuth Desktop app.
2. Save its client-secret JSON outside this repository.
3. Choose an external location for the generated OAuth token.
4. By default, place the files at:

```text
C:\Users\Kelly\.config\cas-ce-agent\credentials.json
C:\Users\Kelly\.config\cas-ce-agent\token.json
```

The token is created automatically during the first authorization. To use
different locations, set:

```powershell
$env:GOOGLE_CALENDAR_CREDENTIALS_PATH = "C:\secure\google-calendar-client.json"
$env:GOOGLE_CALENDAR_TOKEN_PATH = "C:\secure\google-calendar-token.json"
uv sync --extra google
uv run ce-agent sync-google --calendar "Actuarial CE" --year 2026
```

The first sync opens Google's consent flow. The requested scope is read-only.
Secrets and tokens should never be placed in this repository.

### Calendar event convention

Add these optional lines to an event description:

```text
CE-Type: Professionalism
CE-Organized: Yes
CE-Bias: No
CE-Specific: No
CE-Minutes: 90
CE-Status: completed
CE-Event: CAS Webinar Series
CE-Cost: 100
CE-Source: https://example.org/event
```

Allowed types are `Professionalism`, `General Business`, and `Other Relevant`.
New or changed calendar activities always receive `needs_review=1`. Planned events
do not count toward earned credit.

## Review, monitor, and export

```powershell
uv run ce-agent review
uv run ce-agent add --date 2026-06-26 --title "Example webinar" --minutes 90 `
  --kind Organized --type "Other Relevant" --status completed
uv run ce-agent review --approve 1
uv run ce-agent monitor
uv run ce-agent status --year 2026
uv run ce-agent export --year 2026 --output outputs/2026-CAS-CE-log.xlsx
```

The first monitor run establishes a baseline. Later source-content changes create
alerts in SQLite. Policy changes are marked urgent; event/catalog changes are
informational. A Windows Task Scheduler job can run `monitor` on a schedule, but
it only runs while the machine and network are available.

The export contains completed activities only and preserves the CAS template's
layout. Rows marked `CLASSIFICATION NEEDS REVIEW` should be resolved before an
audit submission.

## Alert delivery

The Codex automation **Monthly CAS CE policy and events alert** runs at 9:00 AM
local time on the first day of each month. It reviews the local log and current
official sources, then emails the report to `kellyskogheim@gmail.com` through the
connected Gmail account.

The `alerts` table remains the durable local outbox. Scheduled delivery requires
the computer and local Codex environment to be available, with working network
access and Gmail authorization, when the automation runs.
