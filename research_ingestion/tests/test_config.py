import json
import os

from research_ingestion.config import load_config


def test_dotenv_fills_missing_values_without_overriding_process_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "timezone": "Australia/Sydney",
        "email_recipient": "reader@example.test",
        "sources": {},
        "ai": {},
    }), encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DOTENV_ONLY=from-file\nDOTENV_PRECEDENCE=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DOTENV_ONLY", raising=False)
    monkeypatch.setenv("DOTENV_PRECEDENCE", "from-process")

    load_config(config_path, env_path=env_path)

    assert os.environ["DOTENV_ONLY"] == "from-file"
    assert os.environ["DOTENV_PRECEDENCE"] == "from-process"
