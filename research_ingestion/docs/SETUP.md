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

## 4. Gmail OAuth

1. Create a Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen for personal use.
3. Create an OAuth client of type **Desktop app**.
4. Download the client JSON to `secrets/gmail_client_secret.json`.
5. Set `GMAIL_SENDER` to the sending Gmail address.
6. Run a one-day command without `--no-email`. A browser opens once for consent;
   the refresh token is saved to ignored `secrets/gmail_token.json`.

Only the narrow `gmail.send` scope is requested. The pipeline cannot read,
delete, or modify mailbox contents.

## 5. Test and schedule

```powershell
python -m pytest
python -m research_ingestion.cli run --date 2026-08-13 --no-email
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -PythonExe .\.venv\Scripts\python.exe
```

The task runs at 22:00 and Windows starts a missed invocation when the machine
next becomes available. `--catch-up` processes dates after the last successful
state marker. Long outages can still exceed the retained history of RSS feeds;
date-queryable APIs are not affected by that feed limitation.
