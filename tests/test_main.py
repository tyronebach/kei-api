from main import health


def test_health_checks_db():
    result = health()
    assert result == {"status": "ok"}
