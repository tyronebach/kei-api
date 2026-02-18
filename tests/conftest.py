import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.connection import Base
from dependencies import AgentPrincipal


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def admin_agent():
    return AgentPrincipal(
        agent_id="admin",
        allowed_scopes=["*"],
        permissions=["read", "write"],
    )


@pytest.fixture
def salon_agent():
    return AgentPrincipal(
        agent_id="rem",
        allowed_scopes=["salon"],
        permissions=["read", "write"],
    )


@pytest.fixture
def read_only_agent():
    return AgentPrincipal(
        agent_id="anastasia",
        allowed_scopes=["*"],
        permissions=["read"],
    )
