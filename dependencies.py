import hashlib
import logging
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from db.connection import get_db
from db.models import AgentToken

security = HTTPBearer()
logger = logging.getLogger(__name__)
VALID_TOKEN_PERMISSIONS = {"read", "write"}


@dataclass
class AgentPrincipal:
    agent_id: str
    allowed_scopes: list[str]
    permissions: list[str]

    def can_access_scope(self, scope: str) -> bool:
        return "*" in self.allowed_scopes or scope in self.allowed_scopes

    def can_write(self) -> bool:
        return "write" in self.permissions


def validate_scope(scope: str):
    if scope not in settings.valid_scopes:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scope: '{scope}'. Valid scopes: {settings.valid_scopes}",
        )


def require_scope_write(agent: AgentPrincipal, scope: str) -> None:
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(scope)
    if not agent.can_access_scope(scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{scope}'")


def _invalid_token_row(agent_id: str, field: str, reason: str) -> HTTPException:
    logger.error(
        "Invalid agent token row for agent_id=%s: %s %s",
        agent_id,
        field,
        reason,
    )
    return HTTPException(
        status_code=500,
        detail="Invalid agent token configuration",
    )


def _validate_string_list(value, field: str, agent_id: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise _invalid_token_row(agent_id, field, "must be a non-empty list")

    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _invalid_token_row(
                agent_id,
                field,
                "must contain only non-empty strings",
            )
        cleaned.append(item.strip())
    return cleaned


def _principal_from_token_row(agent_token: AgentToken) -> AgentPrincipal:
    allowed_scopes = _validate_string_list(
        agent_token.allowed_scopes,
        "allowed_scopes",
        agent_token.agent_id,
    )
    permissions = _validate_string_list(
        agent_token.permissions,
        "permissions",
        agent_token.agent_id,
    )
    invalid_permissions = sorted(set(permissions) - VALID_TOKEN_PERMISSIONS)
    if invalid_permissions:
        raise _invalid_token_row(
            agent_token.agent_id,
            "permissions",
            f"contains unsupported values: {invalid_permissions}",
        )

    return AgentPrincipal(
        agent_id=agent_token.agent_id,
        allowed_scopes=allowed_scopes,
        permissions=permissions,
    )


def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> AgentPrincipal:
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    agent_token = (
        db.query(AgentToken)
        .filter(AgentToken.token_hash == token_hash)
        .first()
    )

    if agent_token:
        return _principal_from_token_row(agent_token)

    # Canonical admin/operator fallback token.
    if secrets.compare_digest(credentials.credentials, settings.api_token):
        return AgentPrincipal(
            agent_id="admin",
            allowed_scopes=["*"],
            permissions=["read", "write"],
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    if not secrets.compare_digest(credentials.credentials, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return credentials.credentials
