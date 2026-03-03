from main import health, startup_safety_checks


def test_health_checks_db():
    result = health()
    assert result == {"status": "ok"}


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
