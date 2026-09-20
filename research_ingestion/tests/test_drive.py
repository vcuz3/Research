from types import SimpleNamespace

from research_ingestion.drive import safe_drive_filename, upload_accepted_pdfs


def test_safe_drive_filename_removes_invalid_characters():
    assert safe_drive_filename('Alpha: A/B? <Study>') == "Alpha A B Study.pdf"


def test_drive_upload_creates_dated_library_and_deduplicates(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    created_files = []
    folder_counter = iter(["root-id", "year-id", "day-id"])

    class Call:
        def __init__(self, value):
            self.value = value

        def execute(self):
            return self.value

    class Files:
        def list(self, **_kwargs):
            return Call({"files": []})

        def create(self, *, body, fields, media_body=None):
            if body.get("mimeType") == "application/vnd.google-apps.folder":
                return Call({"id": next(folder_counter)})
            created_files.append(body)
            return Call({"id": "file-id"})

    class Service:
        def files(self):
            return Files()

    monkeypatch.setattr("research_ingestion.drive.drive_service", lambda *_args: Service())
    item = SimpleNamespace(
        local_pdf_path=str(pdf),
        content_sha256="abc123",
        title='Useful: Trading/Study?',
        canonical_url="https://example.test/paper",
        source="test",
    )

    result = upload_accepted_pdfs("2026-08-15", [item], {
        "account": "reader@example.test",
        "root_folder_name": "Trading Research Library",
    })

    assert result == {
        "status": "completed",
        "uploaded": 1,
        "already_present": 0,
        "folder_path": "Trading Research Library/2026/2026-08-15",
    }
    assert created_files[0]["name"] == "Useful Trading Study.pdf"
    assert created_files[0]["appProperties"]["sha256"] == "abc123"


def test_drive_desktop_sync_copies_and_hash_deduplicates(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 desktop sync")
    sync_root = tmp_path / "My Drive"
    sync_root.mkdir()
    item = SimpleNamespace(
        local_pdf_path=str(pdf), content_sha256=None, title="Desktop Study",
        canonical_url="https://example.test", source="test",
    )
    config = {
        "mode": "desktop_sync", "sync_root": str(sync_root),
        "root_folder_name": "Trading Research Library",
    }

    first = upload_accepted_pdfs("2026-08-24", [item], config)
    second = upload_accepted_pdfs("2026-08-24", [item], config)

    target = sync_root / "Trading Research Library/2026/2026-08-24/Desktop Study.pdf"
    assert target.read_bytes() == pdf.read_bytes()
    assert first["uploaded"] == 1
    assert second["already_present"] == 1
