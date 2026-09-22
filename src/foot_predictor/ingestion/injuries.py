"""
Ingestion raw.api_football_injuries -> staging.player_injury.

⚠️ Limitation connue de l'endpoint /injuries : chaque entrée signale un match
où un joueur était absent pour blessure/suspension, mais il n'existe aucun
événement "retour de blessure" -- impossible de dériver une end_date fiable
à partir de cette seule source, donc end_date reste toujours NULL ici.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import ApiFootballInjuries, PlayerInjury
from foot_predictor.ingestion.common import get_or_create_player

SOURCE_NAME = "api-football"


def _upsert_player_injury(session: Session, *, player_id: int, start_date: dt.date, injury_type: str | None) -> str:
    """Pas de contrainte unique sur staging.player_injury (PlayerInjury) -> il
    faut requêter avant d'insérer pour rester idempotent (même logique que
    _upsert_lineup_entry dans api_football.py)."""
    existing = session.scalar(
        select(PlayerInjury).where(
            PlayerInjury.player_id == player_id,
            PlayerInjury.start_date == start_date,
            PlayerInjury.injury_type == injury_type,
        )
    )
    if existing is not None:
        return "unchanged"
    session.add(
        PlayerInjury(player_id=player_id, start_date=start_date, end_date=None, injury_type=injury_type)
    )
    session.flush()
    return "created"


def ingest_api_football_injuries(session: Session) -> tuple[int, int]:
    """Renvoie (nb_traitees, nb_ignorees)."""
    rows = session.scalars(select(ApiFootballInjuries)).all()
    processed, skipped = 0, 0

    for row in rows:
        payload = row.raw_payload
        try:
            player_name = payload["player"]["name"]
            start_date = dt.date.fromisoformat(payload["fixture"]["date"][:10])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue

        injury_type = payload.get("reason") or payload.get("type")

        player = get_or_create_player(session, SOURCE_NAME, player_name, full_name=player_name)
        _upsert_player_injury(session, player_id=player.id, start_date=start_date, injury_type=injury_type)
        processed += 1

    session.commit()
    return processed, skipped


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    with get_session() as session:
        n, s = ingest_api_football_injuries(session)
        print(f"Blessures/absences : {n} traitées, {s} ignorées")
