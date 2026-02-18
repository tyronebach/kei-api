import hashlib

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from db.models import AgentToken
from dependencies import get_current_agent, verify_token


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_verify_token_legacy_admin_valid():
    assert verify_token(_creds("test-token")) == "test-token"


def test_get_current_agent_legacy_admin(db_session):
    principal = get_current_agent(_creds("test-token"), db=db_session)
    assert principal.agent_id == "admin"
    assert principal.can_write() is True
    assert principal.can_access_scope("salon") is True


def test_get_current_agent_from_token_table(db_session):
    raw_token = "rem-secret"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db_session.add(
        AgentToken(
            agent_id="rem",
            token_hash=token_hash,
            allowed_scopes=["salon"],
            permissions=["read", "write"],
        )
    )
    db_session.commit()

    principal = get_current_agent(_creds(raw_token), db=db_session)
    assert principal.agent_id == "rem"
    assert principal.allowed_scopes == ["salon"]
    assert principal.can_access_scope("salon") is True
    assert principal.can_access_scope("home") is False


def test_get_current_agent_invalid_token(db_session):
    with pytest.raises(HTTPException) as exc:
        get_current_agent(_creds("bad-token"), db=db_session)
    assert exc.value.status_code == 401
