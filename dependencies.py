import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from db.connection import get_db
from db.models import AgentToken

security = HTTPBearer()


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
        return AgentPrincipal(
            agent_id=agent_token.agent_id,
            allowed_scopes=agent_token.allowed_scopes,
            permissions=agent_token.permissions,
        )

    # Backward-compatible admin token.
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
