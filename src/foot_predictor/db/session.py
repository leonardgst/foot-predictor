"""
Factory de session SQLAlchemy, branchée sur src/foot_predictor/config.py
(get_settings().database_url, qui lit .env.{APP_ENV}).

À placer dans : src/foot_predictor/db/session.py
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from foot_predictor.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Usage :
        with get_session() as session:
            ingest_football_data(session)

    Commit automatique en sortie normale, rollback si une exception est levée,
    fermeture de la session dans tous les cas.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()