# Meijer Saver

A local, human-in-the-loop Python CLI for planning Meijer savings while respecting product-quality
preferences. Development is intentionally incremental, with a review gate after each phase.

## Implemented phases

- Phase 1 provides the CLI, validated settings, SQLite bootstrap, sanitized fixture boundary, and
  offline tests.
- Phase 2 provides dedicated Chrome-profile management and human-in-the-loop Meijer login. It does
  not read Bitwarden, clip coupons, redeem rewards, or change a cart.

### Setup

Python 3.12 or newer is required.

```powershell
uv sync --extra dev
.\.venv\Scripts\Activate.ps1
meijer-saver --help
```

If you prefer not to activate the environment, invoke its commands directly:

```powershell
.\.venv\Scripts\meijer-saver --help
```

Alternatively, create a Python 3.12 virtual environment and install the editable `dev` extra with
pip.

Initialize local application data:

```powershell
.\.venv\Scripts\meijer-saver config show
.\.venv\Scripts\meijer-saver config init
```

By default, Windows data is stored beneath `%LOCALAPPDATA%\meijer-saver`. For disposable tests or
demonstrations, `config show` and `config init` accept `--data-dir PATH`.

### Verification

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
```

## Security boundaries

- Credentials, payment information, and authentication tokens never belong in configuration or
  application tables.
- The future dedicated Chrome profile is sensitive local data and is excluded from Git.
- Browser fixtures must be synthetic or sanitized and must not include authenticated screenshots.
- All future account-changing actions require an explicit preview and approval.
- Checkout will remain human-controlled.

## Dedicated Chrome and login

Set up the isolated profile outside Playwright first:

```powershell
meijer-saver browser setup
```

This opens ordinary Chrome and Bitwarden's official Chrome download page. Do not create another
Chrome person/profile inside the window: the isolated `Default` subprofile is already Coop's entire
dedicated profile. Install Bitwarden, unlock it, optionally pin it, and then close all windows from
that dedicated Chrome instance.

Start the automated login flow afterward:

```powershell
meijer-saver login
```

Choose your Meijer credential in Bitwarden and complete MFA or CAPTCHA yourself. Meijer Saver does
not attach to Chrome, inspect the page, read password fields, click Bitwarden controls, or claim that
authentication succeeded. It opens Meijer's homepage rather than a deep account link; navigate to
Sign In normally. Once you are finished, close all dedicated Chrome windows and explicitly confirm
whether login succeeded. A failed or denied attempt is not recorded. Chrome retains its session and
extension only inside the dedicated profile shown by `meijer-saver config show`.

Session commands:

```powershell
meijer-saver session check
meijer-saver session logout
meijer-saver session clear
```

`session clear` previews the exact path and requires confirmation. It refuses to remove an existing
directory without Meijer Saver's ownership marker, and it rejects normal Chrome and Edge user-data
paths. Clearing removes Meijer cookies and the Bitwarden extension data stored in this dedicated
profile, so the extension must be configured again next time.

Close any Chrome window using the dedicated profile before running these commands. `session check`
reports only whether the isolated profile exists and whether a manual login flow was previously
completed. It intentionally does not verify current Meijer authentication. `session logout` opens
ordinary Chrome for a manual logout and then removes the local completion marker.

Meijer denied access when opened under Playwright automation, so Phase 2 deliberately stops at this
manual-only boundary. Later phases must not attach automation to Meijer unless Meijer provides or
confirms a supported integration method.

## Phase 2 review checklist

- Confirm the CLI naming and output are comfortable.
- Confirm the default local data location is acceptable.
- Run `login`, unlock Bitwarden manually, sign into Meijer, and close dedicated Chrome.
- Run `session check` and confirm it reports manual completion without claiming authentication.
- Run `session logout`, sign out manually, and confirm the local completion marker is cleared.
- Optionally run `session clear` and confirm the displayed path before approving deletion.
- Approve Phase 2 before implementation begins on read-only Meijer scanning.

## Rollback

The foundation creates local data only when `config init` is run. Use `session clear` to safely
remove the marked dedicated Chrome profile. To roll back a test initialization, remove only the
exact directory passed with `--data-dir`; do not remove a shared parent directory.
