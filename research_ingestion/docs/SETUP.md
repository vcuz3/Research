# Setup

## 1. Install

Create a virtual environment, activate it, and install the project:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[email,test]
```

## 2. Source API keys

- Create a free OpenAlex key and set `OPENALEX_API_KEY`.
- Create an Elsevier developer key and set `ELSEVIER_API_KEY`.
- Missing keys cause those sources to be skipped with a warning; other sources continue.

Accepted DOI records can also use the free OpenAlex and Unpaywall APIs to find
declared open-access repository copies. Configure this under
`public_pdf_resolution`; Unpaywall requires a contact email. Resolver calls are
made only after acceptance, so rejected-candidate DOIs are not disclosed.

ScienceDirect uses the Article Metadata API's `STANDARD` view. A paywalled
record can therefore be retained by title and abstract without downloading its
protected PDF. If Elsevier returns HTTP 401, enable the Article Metadata product
for the API key in Elsevier's API-key settings; the pipeline logs the warning
and continues with Crossref/OpenAlex coverage.

arXiv, Crossref, OpenAlex, and ScienceDirect are queried separately across twelve
trading themes. SSRN uses the public Crossref prefix endpoint for `10.2139` and
keeps only `10.2139/ssrn.*` records containing finance/trading language. The
pipeline does not scrape SSRN pages because they reject automated clients.
Consecutive arXiv theme requests are paced three seconds apart to respect its
API guidance.

Pipeline credentials may be stored in the project-root `.env`, which is ignored
by Git and loaded automatically for manual and scheduled runs. Use `.env.example`
as the template. Explicit process or Windows user environment variables take
precedence over `.env`; secrets never belong in `config.json`.

OmniRoute server settings such as `REQUIRE_API_KEY` and `HOSTNAME` are different:
they must be present in the environment of the OmniRoute server when it starts.
Putting them only in this pipeline's `.env` does not reconfigure an already
running OmniRoute process.

## 3. OmniRoute free-only route

Run the self-hosted OmniRoute gateway and create a route whose name contains
`free`, for example `free-research`. Configure that route with only zero-cost
models/providers and remove every billing-enabled fallback. The pipeline cannot
audit provider billing accounts, so this gateway configuration is part of the
zero-cost guarantee.

Set:

```powershell
$env:OMNIROUTE_BASE_URL = "http://127.0.0.1:20128/v1"
$env:OMNIROUTE_MODEL = "free-research"
$env:OMNIROUTE_API_KEY = "<local gateway key if configured>"
```

The pipeline has no alternate model or endpoint. Its local call/input-token caps
are in `config/config.json`. HTTP 402/429 or quota/payment messages stop AI for
the run and appear in the run report.

## 4. Gmail unattended SMTP

1. Enable 2-Step Verification on the sender Google account.
2. Create a dedicated Google app password for this pipeline.
3. Set `GMAIL_SENDER` to the full sender address and store the app password in
   the ignored `.env` variable configured by `email.app_password_env` (currently
   `APP_PASSWORD`). Never use the account's normal password.

The pipeline connects only to `smtp.gmail.com:465` over TLS and sends mail; it
does not request mailbox read/delete access. Google may revoke an app password
after an account-password change or an explicit revocation.

## 5. Google Drive PDF library

1. Install Google Drive for desktop and sign into the configured library account.
2. Set `drive.mode` to `desktop_sync` and `drive.sync_root` to the mounted My
   Drive path, for example `G:\\My Drive` in JSON.
3. Keep Drive for desktop running so it can synchronize local copies.

Accepted local PDFs are copied to `Trading Research Library/YYYY/YYYY-MM-DD/`,
verified by SHA-256, and deduplicated by content hash. Drive for desktop handles
cloud authorization and synchronization.
Items without a public local PDF remain in the JSON/email but are not uploaded.
The daily HTML email renders each title in bold, followed by `abstract:` (if one
exists), `pdf:` availability, and `link:`. A labeled plain-text fallback is included. Rejected items
are written to `data/rejected/YYYY-MM-DD.json` with item-level reasons and
scores; they are not emailed or uploaded.

## 6. Test and schedule

```powershell
python -m pytest
python -m research_ingestion.cli run --date 2026-08-13 --no-email
python -m research_ingestion.cli resolve-pdfs --from 2026-08-15 --to 2026-08-19
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -PythonExe .\.venv\Scripts\python.exe
```

The task runs at 22:00 and Windows starts a missed invocation when the machine
next becomes available. `--catch-up` processes dates after the last successful
state marker. Long outages can still exceed the retained history of RSS feeds;
date-queryable APIs are not affected by that feed limitation.

The installed task calls `scripts/run_scheduled.ps1`. Before ingestion, that
wrapper starts OmniRoute in hidden daemon mode if port 20128 is not listening
and waits up to 90 seconds for readiness. If startup fails, the pipeline still
runs with its documented deterministic fallback and reports the warning.
After ingestion, it retries unresolved accepted PDFs at 1, 3, 7, and 14 days
using only OpenAlex/Unpaywall. These retries do not resend email, rerun AI, or
revisit blocked SSRN landing pages.
