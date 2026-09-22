"""Tests de la réconciliation cross-source (`ingestion/common.py`) : zone qui
a causé le bug des 19 équipes dupliquées (docs/RECAP_PROJET.md, section 9.3).
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from foot_predictor.db.models import Match, MatchSourceMapping, Player, Team, TeamSourceMapping
from foot_predictor.ingestion.common import (
    get_or_create_competition,
    get_or_create_match,
    get_or_create_player,
    get_or_create_team,
    resolve_match_cross_source,
)

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# get_or_create_team
# ---------------------------------------------------------------------------


def test_get_or_create_team_creates_team_from_yaml_mapping(db_session):
    team = get_or_create_team(db_session, "football_data", "Man Utd", {"Man Utd": "Manchester United"})

    assert team.name == "Manchester United"
    mapping = db_session.scalar(
        select(TeamSourceMapping).where(
            TeamSourceMapping.source_name == "football_data",
            TeamSourceMapping.source_ref == "Man Utd",
        )
    )
    assert mapping is not None
    assert mapping.team_id == team.id


def test_get_or_create_team_falls_back_to_source_ref_when_missing_from_yaml(db_session):
    """Comportement du bug historique (section 9.3) : une entrée absente du
    YAML ne lève pas d'erreur, elle crée l'équipe sous son nom brut."""
    team = get_or_create_team(db_session, "football_data", "Ath Bilbao", {})

    assert team.name == "Ath Bilbao"


def test_get_or_create_team_reuses_existing_mapping_over_corrected_yaml(db_session):
    """Documente le comportement actuel (source du bug des 19 doublons,
    cf. README « Point de vigilance transversal ») : une fois qu'un mapping
    (source_name, source_ref) -> team_id est enregistré, il est PRIORISÉ sur
    le YAML, même si le YAML est corrigé après coup. Ne pas casser ce test
    sans avoir conscience de reproduire/lever ce comportement délibérément."""
    first_team = get_or_create_team(db_session, "football_data", "Ath Bilbao", {})
    assert first_team.name == "Ath Bilbao"

    corrected_mapping = {"Ath Bilbao": "Athletic Club"}
    second_team = get_or_create_team(db_session, "football_data", "Ath Bilbao", corrected_mapping)

    assert second_team.id == first_team.id
    assert second_team.name == "Ath Bilbao"  # PAS "Athletic Club", malgré le YAML corrigé

    duplicate = db_session.scalar(select(Team).where(Team.name == "Athletic Club"))
    assert duplicate is None


def test_get_or_create_team_normalizes_understat_underscore(db_session):
    """Understat fournit des noms avec underscores ('Manchester_United') ;
    ils doivent être normalisés en espaces avant tout lookup, pour retrouver
    l'équipe canonique déjà créée par une autre source (football-data)."""
    canonical = get_or_create_team(
        db_session, "football_data", "Manchester United", {"Manchester United": "Manchester United"}
    )

    understat_team = get_or_create_team(db_session, "understat", "Manchester_United", {})

    assert understat_team.id == canonical.id

    mapping = db_session.scalar(
        select(TeamSourceMapping).where(
            TeamSourceMapping.source_name == "understat",
            TeamSourceMapping.source_ref == "Manchester United",
        )
    )
    assert mapping is not None, "le mapping enregistré doit utiliser le source_ref normalisé (espace, pas underscore)"


def test_get_or_create_team_second_call_reuses_mapping_without_creating_duplicate(db_session):
    first = get_or_create_team(db_session, "understat", "Arsenal", {})
    second = get_or_create_team(db_session, "understat", "Arsenal", {})

    assert first.id == second.id
    teams = db_session.scalars(select(Team).where(Team.name == "Arsenal")).all()
    assert len(teams) == 1


# ---------------------------------------------------------------------------
# get_or_create_competition
# ---------------------------------------------------------------------------


def test_get_or_create_competition_raises_on_unknown_source_ref(db_session):
    with pytest.raises(ValueError, match="Compétition inconnue"):
        get_or_create_competition(db_session, "football_data", "UNKNOWN", {})


def test_get_or_create_competition_reuses_existing_by_canonical_name(db_session):
    mapping = {"E0": {"name": "Premier League", "country": "England"}}
    first = get_or_create_competition(db_session, "football_data", "E0", mapping)
    second = get_or_create_competition(db_session, "understat", "epl", {"epl": {"name": "Premier League"}})

    assert first.id == second.id


# ---------------------------------------------------------------------------
# resolve_match_cross_source
# ---------------------------------------------------------------------------


@pytest.fixture
def match_context(make_competition, make_season, make_team):
    competition = make_competition()
    season = make_season(competition.id)
    home = make_team("Home FC")
    away = make_team("Away FC")
    return competition, season, home, away


def test_resolve_match_cross_source_uses_existing_mapping_directly(db_session, match_context, make_match):
    competition, season, home, away = match_context
    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
    )
    # Premier appel : pas encore de mapping, résolution par clé naturelle.
    resolved_first = resolve_match_cross_source(
        db_session,
        "understat",
        "understat-ref-1",
        home_team_id=home.id,
        away_team_id=away.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),
    )
    assert resolved_first.id == match.id

    # Deuxième appel : doit emprunter le chemin rapide via le mapping déjà
    # enregistré, sans dépendre de la clé naturelle.
    resolved_second = resolve_match_cross_source(
        db_session,
        "understat",
        "understat-ref-1",
        home_team_id=home.id,
        away_team_id=away.id,
        match_date=dt.datetime(1999, 1, 1, tzinfo=dt.timezone.utc),  # date absurde : ignorée si mapping trouvé
    )
    assert resolved_second.id == match.id


def test_resolve_match_cross_source_tolerates_one_day_offset(db_session, match_context, make_match):
    """cf. section 9.3 : St. Pauli-Holstein Kiel, décalage de ±1 jour entre
    Understat (UTC) et football-data (heure locale)."""
    competition, season, home, away = match_context
    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 29, 20, 0, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
    )

    resolved = resolve_match_cross_source(
        db_session,
        "understat",
        "understat-ref-2",
        home_team_id=home.id,
        away_team_id=away.id,
        match_date=dt.datetime(2024, 11, 30, 1, 0, tzinfo=dt.timezone.utc),
    )

    assert resolved is not None
    assert resolved.id == match.id
    mapping = db_session.scalar(
        select(MatchSourceMapping).where(
            MatchSourceMapping.source_name == "understat",
            MatchSourceMapping.source_ref == "understat-ref-2",
        )
    )
    assert mapping is not None and mapping.match_id == match.id


def test_resolve_match_cross_source_beyond_tolerance_returns_none(db_session, match_context, make_match):
    competition, season, home, away = match_context
    make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 27, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
    )

    resolved = resolve_match_cross_source(
        db_session,
        "understat",
        "understat-ref-3",
        home_team_id=home.id,
        away_team_id=away.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),  # 3 jours d'écart
    )

    assert resolved is None


def test_resolve_match_cross_source_ambiguous_pair_within_two_days(db_session, match_context, make_match):
    """Cas limite signalé en section 9.3 comme risque non couvert : si la même
    paire d'équipes joue deux matchs à moins de 2 jours d'écart (championnat +
    coupe la même semaine), la tolérance ±1 jour peut faire matcher les DEUX
    candidats. `resolve_match_cross_source` n'a aucun désambiguïsateur (pas de
    filtre sur la compétition) : il renvoie silencieusement l'un des deux,
    sans garantie sur lequel. Ce test documente que la fonction ne plante pas
    et renvoie bien un des deux matchs candidats -- pas qu'elle choisit le bon."""
    competition, season, home, away = match_context
    match_league = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 29, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
    )
    cup = get_or_create_competition(
        db_session, "football_data", "CUP", {"CUP": {"name": "Coupe nationale"}}
    )
    match_cup = make_match(
        competition_id=cup.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
    )

    resolved = resolve_match_cross_source(
        db_session,
        "understat",
        "understat-ref-ambiguous",
        home_team_id=home.id,
        away_team_id=away.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),
    )

    assert resolved is not None
    assert resolved.id in {match_league.id, match_cup.id}


def test_get_or_create_match_idempotent_update_does_not_duplicate(db_session, match_context):
    competition, season, home, away = match_context

    scheduled = get_or_create_match(
        db_session,
        "football_data",
        "fd-ref-1",
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
        home_goals=None,
        away_goals=None,
        status="scheduled",
    )
    assert scheduled.status == "scheduled"

    played = get_or_create_match(
        db_session,
        "football_data",
        "fd-ref-1",
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2024, 11, 30, tzinfo=dt.timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
        home_goals=2,
        away_goals=1,
        status="played",
    )

    assert played.id == scheduled.id
    assert played.status == "played"
    assert played.home_goals == 2

    matches = db_session.scalars(select(Match).where(Match.home_team_id == home.id)).all()
    assert len(matches) == 1


# ---------------------------------------------------------------------------
# get_or_create_player
# ---------------------------------------------------------------------------


def test_get_or_create_player_resolves_by_name_and_birthdate(db_session):
    player = get_or_create_player(
        db_session,
        "api_football",
        "af-player-1",
        full_name="Kylian Mbappe",
        birth_date=dt.date(1998, 12, 20),
    )
    same_player = get_or_create_player(
        db_session,
        "understat",
        "understat-player-1",
        full_name="Kylian Mbappe",
        birth_date=dt.date(1998, 12, 20),
    )

    assert same_player.id == player.id


def test_get_or_create_player_different_birthdates_are_distinct_players(db_session):
    player_a = get_or_create_player(
        db_session, "api_football", "af-1", full_name="Homonyme Dupont", birth_date=dt.date(1995, 1, 1)
    )
    player_b = get_or_create_player(
        db_session, "api_football", "af-2", full_name="Homonyme Dupont", birth_date=dt.date(2000, 1, 1)
    )

    assert player_a.id != player_b.id


def test_get_or_create_player_without_birthdate_collides_on_name_only(db_session):
    """Risque d'homonymes assumé et documenté dans common.py / RECAP section 7 :
    sans date de naissance, deux joueurs distincts portant le même nom sont
    fusionnés sous la même entité `Player`."""
    player_a = get_or_create_player(db_session, "understat", "u-1", full_name="Jean Dupont")
    player_b = get_or_create_player(db_session, "understat", "u-2", full_name="Jean Dupont")

    assert player_a.id == player_b.id
