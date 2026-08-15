# Trading Research Ingestion

Daily local collection of publicly accessible trading research. The pipeline
discovers papers and reports, downloads public PDFs, extracts text, classifies
relevance through a self-hosted free-only OmniRoute route, writes JSON manifests,
and emails a top-25 reading list through Gmail OAuth.

See `PROJECT_GUIDE.md` for commands and `docs/SETUP.md` for configuration.
Project credentials can be stored in an ignored `.env`; it is loaded
automatically without overriding explicitly set process environment variables.
