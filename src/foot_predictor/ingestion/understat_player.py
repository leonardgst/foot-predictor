"""
Ingestion raw.understat_player_match -> mise à jour xg/xa/npxg dans staging.player_match_stats.

Ne crée JAMAIS de ligne : complète une ligne déjà créée par l'ingestion
API-Football (comme understat.py le fait déjà au niveau équipe pour le xG).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Player, PlayerMatchStats, UnderstatPlayerMatch
from foot_predictor.ingestion.common import get_or_create_team, load_yaml_mapping, resolve_match_cross_source

SOURCE_NAME = "understat"


def ingest_understat_player_match_stats(session: Session) -> tuple[int, int]:
    """Renvoie (nb_traitees, nb_ignorees)."""
    teams_mapping = load_yaml_mapping("understat_teams.yaml")
    rows = session.scalars(select(UnderstatPlayerMatch)).all()
    processed, skipped = 0, 0

    for row in rows:
        payload = row.raw_payload
        match_date = dt.datetime.fromisoformat(payload["match_date"])

        home_team_name = payload["home_team"].replace("_", " ")
        away_team_name = payload["away_team"].replace("_", " ")

        home_team = get_or_create_team(session, SOURCE_NAME, payload["home_team"], teams_mapping)
        away_team = get_or_create_team(session, SOURCE_NAME, payload["away_team"], teams_mapping)

        match_source_ref = f"{payload['match_date']}|{home_team_name}|{away_team_name}"
        match = resolve_match_cross_source(
            session,
            SOURCE_NAME,
            match_source_ref,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            match_date=match_date,
        )
        if match is None:
            skipped += 1
            continue

        # Résolution joueur par nom seul (Understat ne donne pas de date de naissance
        # non plus dans cette structure) -> on cherche un player déjà connu par nom.
        player = session.scalar(select(Player).where(Player.full_name == payload["player_name"]))
        if player is None:
            skipped += 1  # joueur pas encore vu par API-Football -> pas de ligne à compléter
            continue

        stats_row = session.scalar(
            select(PlayerMatchStats).where(
                PlayerMatchStats.match_id == match.id, PlayerMatchStats.player_id == player.id
            )
        )
        if stats_row is None:
            skipped += 1  # pas encore de ligne créée par api-football pour ce (match, joueur)
            continue

        stats_row.xg = payload["xg"]
        stats_row.xa = payload["xa"]
        stats_row.npxg = payload["npxg"]
        session.flush()
        processed += 1

    session.commit()
    return processed, skipped


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    with get_session() as session:
        n, s = ingest_understat_player_match_stats(session)
        print(f"{n} lignes de xG joueur traitées, {s} ignorées.")
