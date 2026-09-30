"""Porte unique de lecture des matchs : filtre du scellé en SQL (base de test)."""

from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.db.models import Competition, Match, Season, Team, TeamMatch
from foot_predictor.features.sources import load_matches

pytestmark = pytest.mark.db


@pytest.fixture
def league(db_session):
    """Un championnat synthétique, deux équipes et trois matchs de part et d'autre du scellé."""
    competition = Competition(name="Ligue synthétique", country="Nulle part", api_league_id=999_101, kind="league")
    db_session.add(competition)
    db_session.flush()
    seasons = {}
    for year in (2024, 2025):
        season = Season(
            competition_id=competition.id,
            label=f"{year}-{year + 1}",
            year=year,
            start_date=dt.date(year, 7, 1),
            end_date=dt.date(year + 1, 6, 30),
        )
        db_session.add(season)
        db_session.flush()
        seasons[year] = season
    home, away = Team(name="Équipe A", origin="hors_api"), Team(name="Équipe B", origin="hors_api")
    db_session.add_all([home, away])
    db_session.flush()
    dates = [
        (2024, dt.datetime(2025, 5, 20, 19, 0, tzinfo=dt.UTC)),
        (2024, dt.datetime(2025, 6, 30, 23, 30, tzinfo=dt.UTC)),  # dernier instant lisible
        (2025, dt.datetime(2025, 7, 1, 0, 0, tzinfo=dt.UTC)),  # premier instant scellé
        (2025, dt.datetime(2025, 8, 16, 15, 0, tzinfo=dt.UTC)),
    ]
    for year, date in dates:
        match = Match(
            competition_id=competition.id,
            season_id=seasons[year].id,
            match_date=date,
            home_team_id=home.id,
            away_team_id=away.id,
            home_goals_90=1,
            away_goals_90=0,
            status="played",
            origin="hors_api",
            round="Regular Season - 1",
        )
        db_session.add(match)
        db_session.flush()
        db_session.add_all(
            [
                TeamMatch(match_id=match.id, team_id=home.id, is_home=True, goals_for=1, goals_against=0),
                TeamMatch(match_id=match.id, team_id=away.id, is_home=False, goals_for=0, goals_against=1),
            ]
        )
    db_session.flush()
    return competition


def test_the_gate_filters_sealed_matches_in_sql(db_session, league):
    frame = load_matches(db_session, competition_ids=[league.id])
    assert len(frame) == 2
    assert frame["match_date"].max().date() == dt.date(2025, 6, 30)
    assert frame["is_regular_season"].all()
    assert list(frame["home_goals_90"]) == [1, 1]


def test_until_is_a_strict_upper_bound(db_session, league):
    frame = load_matches(db_session, competition_ids=[league.id], until=dt.date(2025, 6, 30))
    assert len(frame) == 1


def test_until_after_the_seal_does_not_lift_it(db_session, league):
    frame = load_matches(db_session, competition_ids=[league.id], until=dt.date(2026, 1, 1))
    assert len(frame) == 2


def test_sealed_test_reads_everything_and_logs(db_session, league, tmp_path):
    log = tmp_path / "journal.md"
    frame = load_matches(
        db_session, competition_ids=[league.id], sealed_test=True, experiment="experiments/essai.yaml", sealed_log=log
    )
    assert len(frame) == 4
    assert "2 match(s) scellé(s) lus" in log.read_text(encoding="utf-8")


def test_missing_values_stay_empty(db_session, league):
    frame = load_matches(db_session, competition_ids=[league.id])
    assert frame["home_shots_api"].isna().all()  # aucune statistique : vide, jamais 0
    assert frame["home_xg_api"].isna().all()


def test_football_data_shots_are_exposed(db_session, league):
    """Tirs de football-data (migration 0005) : par côté, vides si absents."""
    from sqlalchemy import select

    from foot_predictor.db.models import TeamMatchStatsExternal

    first = db_session.scalars(
        select(Match).where(Match.competition_id == league.id).order_by(Match.match_date).limit(1)
    ).one()
    home_tm = db_session.scalars(select(TeamMatch).where(TeamMatch.match_id == first.id, TeamMatch.is_home)).one()
    db_session.add(
        TeamMatchStatsExternal(source="football_data", team_match_id=home_tm.id, shots=13, shots_on_target=4)
    )
    db_session.flush()
    frame = load_matches(db_session, competition_ids=[league.id])
    assert (frame.loc[0, "home_shots_fd"], frame.loc[0, "home_sot_fd"]) == (13, 4)
    assert frame["away_shots_fd"].isna().all()
    assert frame.loc[1, ["home_shots_fd", "home_sot_fd"]].isna().all()


def test_odds_are_read_only_before_the_seal(db_session, league):
    """Les cotes passent par la porte : le filtre du scellé est dans la requête (ADR-0036)."""
    from foot_predictor.db.models import MatchOdds
    from foot_predictor.features.sources import load_odds

    matches = db_session.query(Match).filter(Match.competition_id == league.id).order_by(Match.match_date).all()
    for match in matches:
        db_session.add(
            MatchOdds(
                match_id=match.id, source="football_data", version="avant_cloture",
                odds_over_2_5=1.9, odds_under_2_5=1.95, odds_column="Avg",
            )
        )  # fmt: skip
    db_session.flush()
    odds = load_odds(db_session)
    odds = odds[odds["match_id"].isin([m.id for m in matches])]
    assert sorted(odds["match_id"]) == sorted(m.id for m in matches[:2])  # les deux matchs d'avant le 1er juillet
    assert odds["odds_over_2_5"].tolist() == [1.9, 1.9]
