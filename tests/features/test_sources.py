"""Porte unique de lecture des matchs : filtre du scellé en SQL (base de test)."""

from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.db.models import Competition, Match, Season, Team, TeamMatch
from foot_predictor.features.sources import load_matches
from foot_predictor.seal import H1_SEALED_EXPERIMENT, SEALED_DONE, SealViolation

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


def test_opening_for_inference_is_refused_before_the_h1_test_and_reads_nothing(db_session, league, tmp_path):
    log = tmp_path / "journal.md"
    log.write_text(
        f"| 2026-10-22 08:03 | abc | {H1_SEALED_EXPERIMENT} | accès autorisé, résultat à compléter |\n", "utf-8"
    )
    with pytest.raises(SealViolation, match="pas terminé"):
        load_matches(None, competition_ids=[league.id], opened_for_inference=True, sealed_log=log)  # None : jamais lu


def test_opening_for_inference_reads_the_sealed_history_without_logging(db_session, league, tmp_path):
    log = tmp_path / "journal.md"
    log.write_text(f"| 2026-10-22 12:05 | def | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport y |\n", "utf-8")
    before = log.read_text(encoding="utf-8")
    frame = load_matches(db_session, competition_ids=[league.id], opened_for_inference=True, sealed_log=log)
    assert len(frame) == 4 and frame["match_date"].max().date() == dt.date(2025, 8, 16)
    assert log.read_text(encoding="utf-8") == before  # garde par le code, aucune ligne au journal (ADR-0045)
    closed = load_matches(db_session, competition_ids=[league.id], until=dt.date(2026, 1, 1))
    assert len(closed) == 2  # sans l'option, rien ne change


def test_opening_for_inference_is_not_a_sealed_test(db_session, league, tmp_path):
    with pytest.raises(ValueError, match="s'excluent"):
        load_matches(db_session, sealed_test=True, experiment="experiments/x.yaml", opened_for_inference=True)


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


@pytest.fixture
def sheets(db_session, league):
    """Feuilles de match des quatre matchs : un titulaire et un remplaçant par équipe, un entraîneur à domicile."""
    from foot_predictor.db.models import Coach, Lineup, Player, PlayerMatchStats

    coach = Coach(api_coach_id=999_501, name="Entraîneur A")
    starter = Player(full_name="Joueur 1", api_player_id=999_601, birth_date=dt.date(1995, 3, 1))
    bench = Player(full_name="Joueur 2", api_player_id=999_602)  # sans date de naissance
    db_session.add_all([coach, starter, bench])
    db_session.flush()
    matches = db_session.query(Match).filter(Match.competition_id == league.id).order_by(Match.match_date).all()
    for match in matches:
        home = db_session.query(TeamMatch).filter(TeamMatch.match_id == match.id, TeamMatch.is_home).one()
        home.coach_id, home.formation = coach.id, "4-3-3"
        db_session.add_all(
            [
                Lineup(match_id=match.id, team_id=match.home_team_id, player_id=starter.id, started=True, shirt_number=9),
                Lineup(match_id=match.id, team_id=match.home_team_id, player_id=bench.id, started=False),
                PlayerMatchStats(match_id=match.id, player_id=starter.id, team_id=match.home_team_id, minutes=90, rating=7.3),
            ]
        )  # fmt: skip
    db_session.flush()
    return matches


def test_lineups_are_read_only_before_the_seal(db_session, league, sheets):
    from foot_predictor.features.sources import load_lineups

    frame = load_lineups(db_session, competition_ids=[league.id])
    assert len(frame) == 4  # 2 joueurs × les 2 matchs d'avant le 1er juillet
    assert frame["match_date"].max().date() == dt.date(2025, 6, 30)
    assert set(frame["match_id"]) == {m.id for m in sheets[:2]}
    assert frame["started"].tolist() == [True, False, True, False]  # titulaires d'abord
    assert len(load_lineups(db_session, competition_ids=[league.id], until=dt.date(2025, 6, 30))) == 2


def test_lineups_keep_missing_statistics_empty(db_session, league, sheets):
    from foot_predictor.features.sources import load_lineups

    frame = load_lineups(db_session, competition_ids=[league.id])
    starters, bench = frame[frame["started"]], frame[~frame["started"]]
    assert starters["rating"].tolist() == [7.3, 7.3] and starters["minutes"].tolist() == [90, 90]
    assert starters["api_player_id"].tolist() == [999_601, 999_601]
    assert bench["rating"].isna().all() and bench["minutes"].isna().all()  # pas de statistiques : vide, jamais 0
    assert bench["birth_date"].isna().all() and starters["birth_date"].notna().all()


def test_lineups_of_sealed_matches_need_the_sealed_test_and_are_logged(db_session, league, sheets, tmp_path):
    from foot_predictor.features.sources import load_lineups

    log = tmp_path / "journal.md"
    frame = load_lineups(
        db_session, competition_ids=[league.id], sealed_test=True, experiment="experiments/essai.yaml", sealed_log=log
    )
    assert len(frame) == 8
    assert "2 match(s) scellé(s) lus" in log.read_text(encoding="utf-8")


def test_sealed_compositions_open_to_inference_only_after_the_h2_test_and_log_nothing(
    db_session, league, sheets, tmp_path
):
    """ADR-0052 : `opened_for_inference` lève le filtre des compositions et des feuilles de match, sans journal."""
    from foot_predictor.features.sources import load_lineups, load_team_sheets
    from foot_predictor.seal import H1_SEALED_EXPERIMENT, H2_SEALED_EXPERIMENT, SEALED_DONE, SealViolation

    log = tmp_path / "journal.md"
    log.write_text(f"| x | y | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport a |" + chr(10), encoding="utf-8")
    for load in (load_lineups, load_team_sheets):
        with pytest.raises(SealViolation, match="n'est pas terminé"):  # refus avant toute lecture
            load(None, competition_ids=[league.id], opened_for_inference=True, sealed_log=log)
        with pytest.raises(ValueError, match="s'excluent"):
            load(db_session, sealed_test=True, experiment="experiments/x.yaml", opened_for_inference=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"| x | y | {H2_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport b |" + chr(10))
    before = log.read_text(encoding="utf-8")
    lineups = load_lineups(db_session, competition_ids=[league.id], opened_for_inference=True, sealed_log=log)
    team_sheets = load_team_sheets(db_session, competition_ids=[league.id], opened_for_inference=True, sealed_log=log)
    assert len(lineups) == 8 and lineups["match_date"].max().date() > dt.date(2025, 6, 30)  # matchs scellés inclus
    assert len(team_sheets) == 8
    assert log.read_text(encoding="utf-8") == before  # aucune ligne de journal par lecture
    assert len(load_lineups(db_session, competition_ids=[league.id])) == 4  # sans ouverture : toujours filtré


def test_team_sheets_give_the_coach_and_leave_unknowns_empty(db_session, league, sheets):
    from foot_predictor.features.sources import load_team_sheets

    frame = load_team_sheets(db_session, competition_ids=[league.id])
    assert len(frame) == 4  # 2 équipes × 2 matchs d'avant le scellé
    home, away = frame[frame["is_home"]], frame[~frame["is_home"]]
    assert home["api_coach_id"].tolist() == [999_501, 999_501] and home["formation"].tolist() == ["4-3-3"] * 2
    assert away["api_coach_id"].isna().all() and away["coach_id"].isna().all()
    assert frame["match_date"].max().date() == dt.date(2025, 6, 30)
