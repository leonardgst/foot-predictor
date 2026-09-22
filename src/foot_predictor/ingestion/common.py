"""
Fonctions de résolution partagées entre les scripts d'ingestion raw -> staging.

Principe de réconciliation (cf. recap_etape2_schema_tables.md, section 2) :
Pour une entité (équipe, compétition, joueur) rencontrée dans une source donnée :
  1. On cherche d'abord dans <entity>_source_mapping (source_name, source_ref).
     Si trouvé -> on a déjà résolu cette entité par le passé, on renvoie son id.
  2. Sinon, on regarde le mapping manuel (fichier YAML) pour trouver le nom
     canonique associé à ce source_ref.
  3. On cherche/crée l'entité par son nom canonique dans staging.
  4. On crée la ligne de mapping (source_name, source_ref) -> entity_id, pour que
     l'étape 1 fonctionne directement la prochaine fois (idempotence).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

import datetime as dt

from sqlalchemy import Date, cast, func

from foot_predictor.db.models import (
    Competition,
    CompetitionSourceMapping,
    Match,
    MatchSourceMapping,
    Player,
    PlayerSourceMapping,
    Season,
    Team,
    TeamMatch,
    TeamSourceMapping,
)

MAPPINGS_DIR = Path(__file__).parent / "mappings"


def load_yaml_mapping(filename: str) -> dict[str, Any]:
    path = MAPPINGS_DIR / filename
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_or_create_competition(
    session: Session,
    source_name: str,
    source_ref: str,
    competitions_mapping: dict[str, dict[str, str]],
) -> Competition:
    existing_mapping = session.scalar(
        select(CompetitionSourceMapping).where(
            CompetitionSourceMapping.source_name == source_name,
            CompetitionSourceMapping.source_ref == source_ref,
        )
    )
    if existing_mapping is not None:
        return session.get(Competition, existing_mapping.competition_id)

    info = competitions_mapping.get(source_ref)
    if info is None:
        raise ValueError(
            f"Compétition inconnue pour source_ref={source_ref!r} (source={source_name!r}). "
            f"Ajouter une entrée dans mappings/{source_name}_competitions.yaml."
        )
    canonical_name = info["name"]
    country = info.get("country")

    competition = session.scalar(select(Competition).where(Competition.name == canonical_name))
    if competition is None:
        competition = Competition(name=canonical_name, country=country)
        session.add(competition)
        session.flush()  # pour obtenir competition.id

    session.add(
        CompetitionSourceMapping(
            competition_id=competition.id, source_name=source_name, source_ref=source_ref
        )
    )
    session.flush()
    return competition


def get_or_create_season(session: Session, competition_id: int, label: str) -> Season:
    season = session.scalar(
        select(Season).where(Season.competition_id == competition_id, Season.label == label)
    )
    if season is not None:
        return season

    start_year = int(label.split("-")[0])
    season = Season(
        competition_id=competition_id,
        label=label,
        start_date=f"{start_year}-07-01",
        end_date=f"{start_year + 1}-06-30",
    )
    session.add(season)
    session.flush()
    return season

def _normalize_source_ref(source_name: str, source_ref: str) -> str:
    """Certaines sources ont des conventions de nommage à corriger avant tout
    lookup dans le mapping YAML ou dans staging.team.

    Understat utilise des underscores à la place des espaces dans les noms
    d'équipe bruts (ex. 'Manchester_United'), alors que le mapping YAML et
    le référentiel canonique staging.team utilisent des espaces. Sans cette
    normalisation, teams_mapping.get(source_ref) échoue silencieusement et
    retombe sur source_ref lui-même -> création d'une équipe dupliquée
    distincte de l'équipe déjà connue (cf. bug diagnostiqué le 24/07)."""
    if source_name == "understat":
        return source_ref.replace("_", " ")
    return source_ref

def get_or_create_team(
    session: Session,
    source_name: str,
    source_ref: str,
    teams_mapping: dict[str, str],
) -> Team:
    source_ref = _normalize_source_ref(source_name, source_ref)
    existing_mapping = session.scalar(
        select(TeamSourceMapping).where(
            TeamSourceMapping.source_name == source_name,
            TeamSourceMapping.source_ref == source_ref,
        )
    )
    if existing_mapping is not None:
        return session.get(Team, existing_mapping.team_id)

    canonical_name = teams_mapping.get(source_ref, source_ref)

    team = session.scalar(select(Team).where(Team.name == canonical_name))
    if team is None:
        team = Team(name=canonical_name)
        session.add(team)
        session.flush()

    session.add(TeamSourceMapping(team_id=team.id, source_name=source_name, source_ref=source_ref))
    session.flush()
    return team


def get_or_create_match(
    session: Session,
    source_name: str,
    source_ref: str,
    *,
    competition_id: int,
    season_id: int,
    match_date,
    home_team_id: int,
    away_team_id: int,
    home_goals: int | None,
    away_goals: int | None,
    status: str,
) -> Match:
    existing_mapping = session.scalar(
        select(MatchSourceMapping).where(
            MatchSourceMapping.source_name == source_name,
            MatchSourceMapping.source_ref == source_ref,
        )
    )
    if existing_mapping is not None:
        match = session.get(Match, existing_mapping.match_id)
        # Idempotent update : un match "scheduled" peut redevenir "played" avec un score
        # lors d'un run ultérieur -> on met à jour plutôt que d'ignorer.
        match.home_goals = home_goals
        match.away_goals = away_goals
        match.status = status
        session.flush()
        return match

    match = Match(
        competition_id=competition_id,
        season_id=season_id,
        match_date=match_date,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_goals=home_goals,
        away_goals=away_goals,
        status=status,
    )
    session.add(match)
    session.flush()

    session.add(MatchSourceMapping(match_id=match.id, source_name=source_name, source_ref=source_ref))
    session.flush()
    return match


def get_or_create_team_match(
    session: Session,
    *,
    match_id: int,
    team_id: int,
    is_home: bool,
    goals_for: int | None,
    goals_against: int | None,
) -> TeamMatch:
    team_match = session.scalar(
        select(TeamMatch).where(TeamMatch.match_id == match_id, TeamMatch.team_id == team_id)
    )
    if team_match is not None:
        team_match.goals_for = goals_for
        team_match.goals_against = goals_against
        session.flush()
        return team_match

    team_match = TeamMatch(
        match_id=match_id,
        team_id=team_id,
        is_home=is_home,
        goals_for=goals_for,
        goals_against=goals_against,
    )
    session.add(team_match)
    session.flush()
    return team_match


def resolve_match_cross_source(
    session: Session,
    source_name: str,
    source_ref: str,
    *,
    home_team_id: int,
    away_team_id: int,
    match_date: dt.datetime,
) -> Match | None:
    """
    Résout un match provenant d'une source qui n'a pas créé ce match en premier
    (ex. Transfermarkt/Understat, alors que football-data a créé le match).

    1. Cherche d'abord dans match_source_mapping pour cette source -> rapide, direct.
    2. Sinon, cherche le match existant par clé naturelle (équipes + date, à la
       journée près) et enregistre le mapping pour la prochaine fois.

    Renvoie None si aucun match correspondant n'existe encore en staging (dans ce
    cas, la ligne raw ne peut pas être rattachée -> à traiter après coup, une fois
    que football-data aura créé le match, ou en la journalisant pour revue).
    """
    existing_mapping = session.scalar(
        select(MatchSourceMapping).where(
            MatchSourceMapping.source_name == source_name,
            MatchSourceMapping.source_ref == source_ref,
        )
    )
    if existing_mapping is not None:
        return session.get(Match, existing_mapping.match_id)

    # Tolérance de ±1 jour : certaines sources encodent l'horodatage en UTC,
    # d'autres en heure locale avant de tronquer à la date -- un match joué
    # tard le soir peut basculer sur le jour calendaire suivant selon la
    # source (cf. diagnostic du 24/07 : St. Pauli-Holstein Kiel, Genoa-Atalanta).
    date_min = match_date.date() - dt.timedelta(days=1)
    date_max = match_date.date() + dt.timedelta(days=1)

    match = session.scalar(
        select(Match).where(
            Match.home_team_id == home_team_id,
            Match.away_team_id == away_team_id,
            cast(Match.match_date, Date).between(date_min, date_max),
        )
    )
    if match is None:
        return None

    session.add(MatchSourceMapping(match_id=match.id, source_name=source_name, source_ref=source_ref))
    session.flush()
    return match


def get_or_create_player(
    session: Session,
    source_name: str,
    source_ref: str,
    *,
    full_name: str,
    birth_date: dt.date | None = None,
    nationality: str | None = None,
) -> Player:
    """
    Contrairement aux équipes, pas de mapping manuel pour les joueurs (volume trop
    important). Résolution par clé naturelle (nom complet + date de naissance),
    qui est un identifiant suffisamment fiable pour désambiguïser les homonymes.
    """
    existing_mapping = session.scalar(
        select(PlayerSourceMapping).where(
            PlayerSourceMapping.source_name == source_name,
            PlayerSourceMapping.source_ref == source_ref,
        )
    )
    if existing_mapping is not None:
        return session.get(Player, existing_mapping.player_id)

    query = select(Player).where(Player.full_name == full_name)
    if birth_date is not None:
        query = query.where(Player.birth_date == birth_date)
    player = session.scalar(query)

    if player is None:
        player = Player(full_name=full_name, birth_date=birth_date, nationality=nationality)
        session.add(player)
        session.flush()

    session.add(PlayerSourceMapping(player_id=player.id, source_name=source_name, source_ref=source_ref))
    session.flush()
    return player


def upsert_team_match_xg(
    session: Session,
    *,
    match_id: int,
    team_id: int,
    xg_for: float | None,
    xg_against: float | None,
) -> TeamMatch | None:
    """Met à jour le xG d'une ligne team_match déjà existante (créée par football-data).
    Ne crée PAS de nouvelle ligne : si team_match n'existe pas encore, renvoie None
    (signale que football-data n'a pas encore ingéré ce match)."""
    team_match = session.scalar(
        select(TeamMatch).where(TeamMatch.match_id == match_id, TeamMatch.team_id == team_id)
    )
    if team_match is None:
        return None
    team_match.xg_for = xg_for
    team_match.xg_against = xg_against
    session.flush()
    return team_match