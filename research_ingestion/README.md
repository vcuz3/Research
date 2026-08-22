# Trading Research Ingestion

Daily local collection of publicly accessible trading research. The pipeline
discovers papers and reports, downloads public PDFs, extracts text, classifies
relevance through a self-hosted free-only OmniRoute route, writes JSON manifests,
and emails a top-25 reading list through Gmail OAuth.

API discovery is split across twelve trading themes rather than one broad
Boolean-like query. SSRN metadata is discovered through its public Crossref DOI
prefix (`10.2139`) because SSRN's own search pages block automated access; the
same local relevance gates apply before any item is accepted.

Manually downloaded public PDFs can be placed in `pdf_downloads/`. Run
`python -m research_ingestion.cli import-pdfs`, or leave them for the scheduled
pipeline: it validates and title-matches them, updates the accepted manifests,
and uploads unique matches to the article date's Google Drive folder.

See `PROJECT_GUIDE.md` for commands and `docs/SETUP.md` for configuration.
Project credentials can be stored in an ignored `.env`; it is loaded
automatically without overriding explicitly set process environment variables.
