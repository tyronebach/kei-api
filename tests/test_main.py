import os
import subprocess
import sys
from pathlib import Path

from main import health, startup_safety_checks

ROOT = Path(__file__).resolve().parents[1]


def test_health_checks_db():
    result = health()
    assert result == {"status": "ok"}


def test_health_logs_db_failures(monkeypatch, caplog):
    class FailingSession:
        def execute(self, statement):
            raise RuntimeError("db is down")

        def close(self):
            pass

    monkeypatch.setattr("main.SessionLocal", lambda: FailingSession())

    with caplog.at_level("ERROR"):
        result = health()

    assert result.status_code == 503
    assert "Health check DB query failed" in caplog.text
    assert "db is down" in caplog.text


def test_db_connection_import_with_absolute_sqlite_url_does_not_create_cwd_data(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    db_path = tmp_path / "custom.db"
    env = {
        **os.environ,
        "KEI_DATABASE_URL": f"sqlite:///{db_path}",
        "KEI_API_TOKEN": "test-token",
        "PYTHONPATH": str(ROOT),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path\n"
                "import db.connection\n"
                "print(Path('data').exists())\n"
            ),
        ],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
    assert not (workdir / "data").exists()


def test_startup_allows_non_default_token(monkeypatch):
    monkeypatch.setattr("main.settings.api_token", "test-token")
    monkeypatch.setattr("main.settings.allow_insecure_default_token", False)
    startup_safety_checks()


def test_startup_rejects_default_token_by_default(monkeypatch):
    monkeypatch.setattr("main.settings.api_token", "changeme")
    monkeypatch.setattr("main.settings.allow_insecure_default_token", False)

    try:
        startup_safety_checks()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "insecure default" in str(exc)


def test_startup_allows_default_token_with_explicit_override(monkeypatch):
    monkeypatch.setattr("main.settings.api_token", "changeme")
    monkeypatch.setattr("main.settings.allow_insecure_default_token", True)
    startup_safety_checks()
