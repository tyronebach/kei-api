import sys
from pathlib import Path

import pytest
import httpx
import typer

CLI_ROOT = Path(__file__).resolve().parents[1]
if str(CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(CLI_ROOT))

from kei.client import KeiClient
from kei import snapshots as snapshot_commands
from kei import summary as summary_commands


def _json_response(status_code: int, payload) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=payload)


def test_resolve_prefix_returns_full_id_without_lookup(monkeypatch):
    monkeypatch.setenv("KEI_API_BASE", "http://testserver")
    monkeypatch.setenv("KEI_API_TOKEN", "token")
    client = KeiClient(scope="salon")
    full_id = "a" * 32

    def fail_lookup(*args, **kwargs):
        raise AssertionError("full IDs should not trigger prefix lookup")

    monkeypatch.setattr(client, "_get", fail_lookup)

    assert client._resolve_prefix(full_id, "/api/entities") == full_id


def test_resolve_prefix_exits_on_lookup_api_error(monkeypatch):
    monkeypatch.setenv("KEI_API_BASE", "http://testserver")
    monkeypatch.setenv("KEI_API_TOKEN", "token")
    client = KeiClient(scope="salon")
    monkeypatch.setattr(
        client,
        "_get",
        lambda *args, **kwargs: _json_response(500, {"detail": "boom"}),
    )

    with pytest.raises(SystemExit):
        client._resolve_prefix("abc", "/api/entities")


def test_resolve_prefix_success(monkeypatch):
    monkeypatch.setenv("KEI_API_BASE", "http://testserver")
    monkeypatch.setenv("KEI_API_TOKEN", "token")
    client = KeiClient(scope="salon")
    row_id = "abcdef1234567890abcdef1234567890"
    monkeypatch.setattr(
        client,
        "_get",
        lambda *args, **kwargs: _json_response(200, {"data": [{"id": row_id}]}),
    )

    assert client._resolve_prefix("abc", "/api/entities") == row_id


def test_pulse_treats_snapshot_404_as_missing(monkeypatch):
    class FakeClient:
        def __init__(self, scope=None):
            self.scope = scope

        def _get(self, path, **kwargs):
            return _json_response(404, {"detail": "No snapshots"})

        def _handle_response(self, response):
            raise AssertionError("404 snapshot response should not be handled as fatal")

        def summary_by_scope(self, **params):
            return {"data": {"scopes": []}}

        def summary_trends(self, **params):
            return {"data": {}}

    monkeypatch.setattr(summary_commands, "KeiClient", FakeClient)

    summary_commands.pulse(ctx=None)


def test_pulse_aborts_on_snapshot_auth_error(monkeypatch):
    class FakeClient:
        def __init__(self, scope=None):
            self.scope = scope

        def _get(self, path, **kwargs):
            return _json_response(401, {"detail": "Invalid token"})

        def _handle_response(self, response):
            raise SystemExit(1)

    monkeypatch.setattr(summary_commands, "KeiClient", FakeClient)

    with pytest.raises(SystemExit):
        summary_commands.pulse(ctx=None)


def test_pulse_aborts_on_summary_failure(monkeypatch):
    class FakeClient:
        def __init__(self, scope=None):
            self.scope = scope

        def _get(self, path, **kwargs):
            return _json_response(404, {"detail": "No snapshots"})

        def _handle_response(self, response):
            raise AssertionError("404 snapshot response should not be handled as fatal")

        def summary_by_scope(self, **params):
            raise SystemExit(1)

    monkeypatch.setattr(summary_commands, "KeiClient", FakeClient)

    with pytest.raises(SystemExit):
        summary_commands.pulse(ctx=None)


def test_snapshot_rich_render_requires_object_response():
    with pytest.raises(typer.Exit) as exc:
        snapshot_commands._render_snapshot([])

    assert exc.value.exit_code == 1


def test_snapshot_rich_render_requires_net_worth():
    with pytest.raises(typer.Exit) as exc:
        snapshot_commands._render_snapshot({"date": "2026-03-20", "data": {}})

    assert exc.value.exit_code == 1
