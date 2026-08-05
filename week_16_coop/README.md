# DG Saver

A local Python CLI for finding unusually strong Dollar General deals, with donation usefulness as
a future ranking signal. Development is incremental and stops for review after every phase.

## Implemented phases

Phase 0 provides:

- the `dg-saver` CLI and non-secret local configuration;
- an idempotent SQLite bootstrap for later phases;
- an offline test and fixture boundary;
- local-data and credential-security rules.

Phase 1 adds a public, read-only automation feasibility probe:

- `probe fixtures` validates extraction contracts entirely offline;
- `probe live` opens headed, ephemeral Chrome and checks the public coupon and weekly-ad pages;
- both modes fail closed when required page signals disappear;
- optional JSON output contains only page status and aggregate signals.

Phase 2 adds public offer extraction and conservative normalization:

- every advertised coupon is loaded before extraction begins;
- coupon type, brand, savings text/cents, visible qualification text, expiration, quantity and
  redemption-limit badges, and issuer are normalized when unambiguous;
- weekly-ad item controls are preserved verbatim and simple price phrases are extracted;
- deterministic IDs allow later scans to compare the same visible offer content;
- incomplete or abbreviated terms remain marked for full-term review.

It does **not** log in, persist a browser profile, normalize offers, clip coupons, or modify an account.
The earlier Meijer browser and session commands have been removed. Existing Meijer profile data is
left untouched and remains excluded from Git.

### Setup

Python 3.12 or newer is required.

```powershell
uv sync --extra dev
.\.venv\Scripts\Activate.ps1
dg-saver --help
```

Activation is optional; commands can be invoked directly:

```powershell
.\.venv\Scripts\dg-saver --help
.\.venv\Scripts\dg-saver config show
.\.venv\Scripts\dg-saver config init
.\.venv\Scripts\dg-saver probe fixtures
.\.venv\Scripts\dg-saver offers fixtures
```

By default, Windows application data is stored under `%LOCALAPPDATA%\dg-saver`. For tests or
demonstrations, configuration commands accept `--data-dir PATH`.

### Preferred store

Save the store label you expect Dollar General to display:

```powershell
.\.venv\Scripts\dg-saver store set "Westland, MI"
.\.venv\Scripts\dg-saver store show
```

The preference is stored at `%LOCALAPPDATA%\dg-saver\dg-saver.preferences.json`. The filename and
the entire `.dg-saver` project-local directory are explicitly ignored by Git. `store clear` removes
only this preferences file.

During `probe live` and `offers live`, DG Saver parses the configured full address, opens Dollar
General's official city store directory, requires exactly one matching address, and obtains its
store number. It applies that official directory result as the ephemeral guest in-store preference,
then reads the Dollar General header back. A missing, ambiguous, or mismatched result fails closed
before scanning. The verified label is included in the output report. Store choice remains in
memory only for that browser run; no persistent Chrome profile is created.

### Verification

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
```

## Security boundaries

- Credentials, cookies, tokens, payment information, addresses, and account identifiers never
  belong in configuration, logs, fixtures, reports, or application tables.
- Browser fixtures must be synthetic or sanitized; authenticated screenshots are prohibited.
- Any future coupon clipping or account mutation must show an exact preview and require approval.
- CAPTCHA, MFA, bot protection, access controls, and retailer restrictions must not be bypassed.
- Checkout and payment submission remain human-controlled.
- Personal application data remains outside Git and ordinary project backups.
- The preferred-store file contains location information, stays under the private data directory,
  and is explicitly ignored as `dg-saver.preferences.json` if placed in the repository.

## Phase 1 live probe

Run the live check explicitly:

```powershell
.\.venv\Scripts\dg-saver probe live
```

The command opens installed Chrome in headed mode with a new ephemeral context, visits only the
public coupon and weekly-ad URLs, counts structural signals, and closes the context. Do not sign in
to the probe window. A successful result demonstrates that public read-only browser extraction is
currently feasible; it is not permission from Dollar General and is not a guarantee that the site
will remain unchanged.

Known limitations:

- the coupon probe repeatedly uses `Load more`, verifies growth after every batch, and succeeds only
  when the loaded count exactly matches the advertised total and the control is gone;
- coupon terms, eligible products, stacking, and expiration dates are not yet normalized;
- weekly-ad offers are counted but not parsed or associated with a selected store;
- the probe does not evaluate robots.txt or retailer terms as authorization for later automation;
- live access may vary by network, region, browser version, and future site changes.

## Phase 2 offer extraction

Run offline normalization first, then explicitly run the live extraction:

```powershell
.\.venv\Scripts\dg-saver offers fixtures
.\.venv\Scripts\dg-saver offers live
```

The default JSON reports are written under `.dg-saver/reports`, which is ignored by Git. Use
`--output PATH` to choose another location. The live command uses two headed ephemeral browser
contexts—one for the fully expanded coupon gallery and one for the embedded weekly-ad viewer—and
closes both without signing in.

Phase 2 intentionally does not claim that gallery summaries are complete legal terms. Many cards
link to separate detail pages, and weekly-ad item controls may omit fine print. Every extracted
record therefore carries `full_terms_review_required: true`; fields that cannot be normalized
reliably remain `null` with a review reason. Phase 2 does not rank deals, infer stacking, select a
store, clip coupons, or access an account.

## Review gate and rollback

Review Phase 2 by running `offers fixtures`, inspecting its JSON, then explicitly running
`offers live`. Confirm that advertised and extracted coupon counts match, weekly offers are
nonzero, the browser closes, and no sign-in occurs. Run tests and lint before accepting Phase 2.

`config init` creates only the exact data directory displayed by `config show`. To roll back a test
initialization, remove only the explicit disposable directory supplied with `--data-dir`. Uninstall
the editable CLI by removing `.venv` or by resynchronizing the environment from another project.

To roll back Phase 2, remove `offers.py`, its tests and JSON fixtures, and the `offers` CLI
registration. Phase 0 configuration and SQLite data require no migration; Phase 1 remains usable.
