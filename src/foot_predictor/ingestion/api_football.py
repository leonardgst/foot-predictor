"""
Ingestion raw.api_football_fixture_detail -> staging (lineups + player_match_stats).

Deux extracteurs indépendants lisent la même table raw (réponse /fixtures?id=
quasi verbatim) :
  - ingest_api_football_lineups       -> staging.lineup
  - ingest_api_football_player_stats  -> staging.player_match_stats

⚠️ L'endpoint /fixtures?id= ne fournit PAS la date de naissance des joueurs
(seulement id, nom, photo). Résolution des joueurs par nom seul -> risque
d'homonymes légèrement plus élevé qu'avec une source qui donnerait la date
de naissance (cf. limitation déjà actée pour les lineups).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import ApiFootballFixtureDetail, Lineup, PlayerMatchStats
from foot_predictor.ingestion.common import (
    get_or_create_player,
    get_or_create_team,
    load_yaml_mapping,
    resolve_match_cross_source,
)

SOURCE_NAME = "api-football"


def _match_context(session: Session, fixture_detail: dict, teams_mapping: dict):
    """Résout home_team/away_team/match, commun aux deux extracteurs."""
    import datetime as dt

    teams = fixture_detail["teams"]
    match_date = dt.datetime.fromisoformat(fixture_detail["fixture"]["date"][:19])
    fixture_id = fixture_detail["fixture"]["id"]

    home_team = get_or_create_team(session, SOURCE_NAME, teams["home"]["name"], teams_mapping)
    away_team = get_or_create_team(session, SOURCE_NAME, teams["away"]["name"], teams_mapping)

    match = resolve_match_cross_source(
        session,
        SOURCE_NAME,
        f"fixture:{fixture_id}",
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        match_date=match_date,
    )
    return home_team, away_team, match


# ---------------------------------------------------------------------------
# Lineups
# ---------------------------------------------------------------------------


def _upsert_lineup_entry(session: Session, *, match_id, team_id, player_id, started, position) -> None:
    existing = session.scalar(
        select(Lineup).where(
            Lineup.match_id == match_id, Lineup.team_id == team_id, Lineup.player_id == player_id
        )
    )
    if existing is not None:
        existing.started = started
        existing.position = position
        session.flush()
        return
    session.add(Lineup(match_id=match_id, team_id=team_id, player_id=player_id, started=started, position=position))
    session.flush()


def ingest_api_football_lineups(session: Session) -> tuple[int, int]:
    teams_mapping = load_yaml_mapping("api_football_teams.yaml")
    rows = session.scalars(select(ApiFootballFixtureDetail)).all()
    processed, skipped = 0, 0

    for row in rows:
        payload = row.raw_payload
        home_team, away_team, match = _match_context(session, payload, teams_mapping)
        if match is None or not payload.get("lineups"):
            skipped += 1
            continue

        lineups = payload["lineups"]
        team_by_side = {lineups[0]["team"]["name"]: home_team, lineups[1]["team"]["name"]: away_team}

        for side_lineup in lineups:
            team = team_by_side.get(side_lineup["team"]["name"])
            if team is None:
                continue
            for slot in side_lineup.get("startXI", []):
                p = slot["player"]
                player = get_or_create_player(session, SOURCE_NAME, p["name"], full_name=p["name"])
                _upsert_lineup_entry(session, match_id=match.id, team_id=team.id, player_id=player.id, started=True, position=p.get("pos"))
            for slot in side_lineup.get("substitutes", []):
                p = slot["player"]
                player = get_or_create_player(session, SOURCE_NAME, p["name"], full_name=p["name"])
                _upsert_lineup_entry(session, match_id=match.id, team_id=team.id, player_id=player.id, started=False, position=p.get("pos"))
        processed += 1

    session.commit()
    return processed, skipped


# ---------------------------------------------------------------------------
# Player match stats
# ---------------------------------------------------------------------------


def _parse_accuracy(value) -> float | None:
    if value is None:
        return None
    text = str(value).replace("%", "").strip()
    if not text or text == "None":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _upsert_player_match_stats(session: Session, *, match_id, player_id, team_id, stats: dict) -> None:
    games = stats.get("games") or {}
    shots = stats.get("shots") or {}
    goals = stats.get("goals") or {}
    passes = stats.get("passes") or {}
    tackles = stats.get("tackles") or {}
    duels = stats.get("duels") or {}
    dribbles = stats.get("dribbles") or {}
    fouls = stats.get("fouls") or {}
    cards = stats.get("cards") or {}

    values = dict(
        team_id=team_id,
        minutes=games.get("minutes"),
        rating=float(games["rating"]) if games.get("rating") else None,
        position_bucket=games.get("position"),
        goals=goals.get("total"),
        assists=goals.get("assists"),
        shots=shots.get("total"),
        shots_on_target=shots.get("on"),
        key_passes=passes.get("key"),
        pass_accuracy_pct=_parse_accuracy(passes.get("accuracy")),
        tackles=tackles.get("total"),
        interceptions=tackles.get("interceptions"),
        duels_total=duels.get("total"),
        duels_won=duels.get("won"),
        dribbles_attempts=dribbles.get("attempts"),
        dribbles_success=dribbles.get("success"),
        dribbled_past=dribbles.get("past"),
        fouls_drawn=fouls.get("drawn"),
        fouls_committed=fouls.get("committed"),
        yellow_cards=cards.get("yellow"),
        red_cards=cards.get("red"),
    )

    existing = session.scalar(
        select(PlayerMatchStats).where(
            PlayerMatchStats.match_id == match_id, PlayerMatchStats.player_id == player_id
        )
    )
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        session.flush()
        return
    session.add(PlayerMatchStats(match_id=match_id, player_id=player_id, **values))
    session.flush()


def ingest_api_football_player_stats(session: Session) -> tuple[int, int]:
    teams_mapping = load_yaml_mapping("api_football_teams.yaml")
    rows = session.scalars(select(ApiFootballFixtureDetail)).all()
    processed, skipped = 0, 0

    for row in rows:
        payload = row.raw_payload
        home_team, away_team, match = _match_context(session, payload, teams_mapping)
        if match is None or not payload.get("players"):
            skipped += 1
            continue

        team_by_name = {home_team.name: home_team, away_team.name: away_team}
        # payload["players"] : liste de 2 blocs {"team": {...}, "players": [...]}
        for team_block in payload["players"]:
            api_team_name = team_block["team"]["name"]
            team = home_team if api_team_name == payload["teams"]["home"]["name"] else away_team

            for player_entry in team_block["players"]:
                p = player_entry["player"]
                stats_list = player_entry.get("statistics") or []
                if not stats_list:
                    continue
                player = get_or_create_player(session, SOURCE_NAME, p["name"], full_name=p["name"])
                _upsert_player_match_stats(
                    session, match_id=match.id, player_id=player.id, team_id=team.id, stats=stats_list[0]
                )
        processed += 1

    session.commit()
    return processed, skipped


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    with get_session() as session:
        n, s = ingest_api_football_lineups(session)
        print(f"Lineups : {n} traitées, {s} ignorées")

    with get_session() as session:
        n, s = ingest_api_football_player_stats(session)
        print(f"Player match stats : {n} traitées, {s} ignorées")
