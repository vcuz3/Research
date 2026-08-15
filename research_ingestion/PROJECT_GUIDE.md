# Trading Research Ingestion Project Guide

## Objective

Build an auditable local ingestion pipeline for public trading-related academic
papers and institutional reports. Outputs are reading aids and source records,
not validated trading evidence.

## Project map

| Concern | Location |
| --- | --- |
| Runtime configuration | `config/config.json` |
| Source adapters | `src/research_ingestion/connectors.py` |
| Filtering and AI classification | `src/research_ingestion/classify.py` |
| Storage and manifests | `src/research_ingestion/storage.py` |
| Gmail delivery | `src/research_ingestion/emailer.py` |
| Scheduling | `scripts/install_scheduled_task.ps1` |
| Tests | `tests/` |
| Durable status | `MEMORY.md` |

## Commands

```powershell
python -m pip install -e .[email,test]
python -m pytest
python -m research_ingestion.cli run --date 2026-08-13 --no-email
python -m research_ingestion.cli run --from 2026-08-01 --to 2026-08-07 --no-email
python -m research_ingestion.cli run --catch-up
```

## Operating conventions

- Calendar timezone: `Australia/Sydney`.
- The scheduled task runs daily at 22:00 and has `StartWhenAvailable` enabled.
- `--catch-up` processes every calendar date after the last successful scheduled
  date through today. API sources are date-queryable; RSS catch-up is limited by
  each feed's retained history.
- Raw PDFs are immutable and named by stable document ID plus content hash.
- The catalogue uses SQLite; per-day accepted and reading manifests are JSON.
- Secrets are environment variables or ignored files under `secrets/`.

## Zero-cost AI boundary

The pipeline calls exactly one local, OpenAI-compatible OmniRoute base URL and
one configured model/route. It does not possess paid-provider credentials and
does not retry through another model or endpoint. Configure that OmniRoute route
to contain only free providers/models and no billing-enabled fallback. Local
per-run call and token estimates are hard caps. HTTP 402/429 and quota-related
responses disable further AI calls for the run and create a warning.

