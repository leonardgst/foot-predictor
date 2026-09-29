"""
Modèles SQLAlchemy — foot-predictor
Reflète le schéma conçu dans recap_etape2_schema_tables.md (raw / staging / features).

À placer dans : src/foot_predictor/db/models.py
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Enum Postgres pour le statut d'un match (créé dans le schéma staging)
match_status_enum = PGEnum(
    "scheduled",
    "played",
    "postponed",
    "cancelled",
    name="match_status",
    schema="staging",
)

# Enum Postgres pour la catégorie de poste brute (4 valeurs API-Football)
position_bucket_enum = PGEnum(
    "Goalkeeper",
    "Defender",
    "Midfielder",
    "Attacker",
    name="position_bucket",
    schema="staging",
)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# staging
# ---------------------------------------------------------------------------


class Competition(Base):
    __tablename__ = "competition"
    __table_args__ = (
        UniqueConstraint("api_league_id", name="uq_competition_api_league_id"),
        CheckConstraint("kind IN ('league', 'cup')", name="ck_competition_kind"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    api_league_id: Mapped[int | None] = mapped_column(Integer)  # migration 0004 (ADR-0008)
    kind: Mapped[str | None] = mapped_column(Text)  # « league » ou « cup »
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompetitionSourceMapping(Base):
    __tablename__ = "competition_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_competition_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("staging.competition.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class Season(Base):
    __tablename__ = "season"
    __table_args__ = (
        UniqueConstraint("competition_id", "year", name="uq_season_competition_year"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("staging.competition.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    year: Mapped[int | None] = mapped_column(SmallInteger)  # année de début, comme l'API (2023 = 2023-24)


class Team(Base):
    __tablename__ = "team"
    __table_args__ = (
        UniqueConstraint("api_team_id", name="uq_team_api_team_id"),
        CheckConstraint("origin IN ('api', 'hors_api')", name="ck_team_origin"),
        CheckConstraint("origin IS DISTINCT FROM 'api' OR api_team_id IS NOT NULL", name="ck_team_api_id_origin"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    api_team_id: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[str | None] = mapped_column(Text)  # « api » ou « hors_api » (football-data seul)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamSourceMapping(Base):
    __tablename__ = "team_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_team_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class Player(Base):
    __tablename__ = "player"
    __table_args__ = (
        UniqueConstraint("api_player_id", name="uq_player_api_player_id"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    api_player_id: Mapped[int | None] = mapped_column(Integer)
    birth_date: Mapped[dt.date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayerSourceMapping(Base):
    __tablename__ = "player_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_player_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class Match(Base):
    __tablename__ = "match"
    __table_args__ = (
        UniqueConstraint("api_fixture_id", name="uq_match_api_fixture_id"),
        CheckConstraint("exclusion_reason IN ('tapis_vert', 'annule', 'abandonne')", name="ck_match_exclusion_reason"),
        CheckConstraint("excluded = (exclusion_reason IS NOT NULL)", name="ck_match_excluded_has_reason"),
        CheckConstraint("origin IN ('api', 'hors_api')", name="ck_match_origin"),
        CheckConstraint("origin IS DISTINCT FROM 'api' OR api_fixture_id IS NOT NULL", name="ck_match_api_id_origin"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("staging.competition.id"), nullable=False, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("staging.season.id"), nullable=False, index=True)
    match_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False, index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False, index=True)
    home_goals: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(match_status_enum, nullable=False, server_default="scheduled")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Migration 0004. home_goals/away_goals : score final (prolongations comprises) ;
    # *_goals_90 : temps réglementaire, la cible de l'ADR-0009.
    api_fixture_id: Mapped[int | None] = mapped_column(BigInteger)
    kickoff_utc: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status_short: Mapped[str | None] = mapped_column(Text)
    round: Mapped[str | None] = mapped_column(Text)
    home_goals_90: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals_90: Mapped[int | None] = mapped_column(SmallInteger)
    home_penalties: Mapped[int | None] = mapped_column(SmallInteger)
    away_penalties: Mapped[int | None] = mapped_column(SmallInteger)
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str | None] = mapped_column(Text)


class MatchSourceMapping(Base):
    __tablename__ = "match_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_match_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class TeamMatch(Base):
    __tablename__ = "team_match"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_team_match"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False, index=True)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    goals_for: Mapped[int | None] = mapped_column(SmallInteger)
    goals_against: Mapped[int | None] = mapped_column(SmallInteger)
    xg_for: Mapped[float | None] = mapped_column(Numeric(4, 2))
    xg_against: Mapped[float | None] = mapped_column(Numeric(4, 2))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Migration 0004
    coach_id: Mapped[int | None] = mapped_column(ForeignKey("staging.coach.id"), index=True)
    formation: Mapped[str | None] = mapped_column(Text)
    unknown_starters: Mapped[int | None] = mapped_column(SmallInteger)  # identifiant absent ou 0 (ADR-0008)
    collision_excluded: Mapped[int | None] = mapped_column(SmallInteger)  # entrées exclues (ADR-0020)


class Coach(Base):
    __tablename__ = "coach"
    __table_args__ = (
        UniqueConstraint("api_coach_id", name="uq_coach_api_coach_id"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    api_coach_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CoachSourceMapping(Base):
    __tablename__ = "coach_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_coach_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("staging.coach.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class TeamMatchStats(Base):
    """Statistiques d'équipe d'un match (bloc `statistics` de l'API), migration 0004."""

    __tablename__ = "team_match_stats"
    __table_args__ = (
        UniqueConstraint("team_match_id", name="uq_team_match_stats"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    team_match_id: Mapped[int] = mapped_column(ForeignKey("staging.team_match.id"), nullable=False)
    shots_on_goal: Mapped[int | None] = mapped_column(SmallInteger)
    shots_off_goal: Mapped[int | None] = mapped_column(SmallInteger)
    shots_total: Mapped[int | None] = mapped_column(SmallInteger)
    shots_blocked: Mapped[int | None] = mapped_column(SmallInteger)
    shots_inside_box: Mapped[int | None] = mapped_column(SmallInteger)
    shots_outside_box: Mapped[int | None] = mapped_column(SmallInteger)
    fouls: Mapped[int | None] = mapped_column(SmallInteger)
    corners: Mapped[int | None] = mapped_column(SmallInteger)
    offsides: Mapped[int | None] = mapped_column(SmallInteger)
    possession_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    yellow_cards: Mapped[int | None] = mapped_column(SmallInteger)
    red_cards: Mapped[int | None] = mapped_column(SmallInteger)
    goalkeeper_saves: Mapped[int | None] = mapped_column(SmallInteger)
    passes_total: Mapped[int | None] = mapped_column(SmallInteger)
    passes_accurate: Mapped[int | None] = mapped_column(SmallInteger)
    passes_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    expected_goals: Mapped[float | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMatchStatsExternal(Base):
    """Tirs d'une équipe dans un match, selon une source externe (football-data), migration 0005.

    Une valeur absente ou illisible dans la source reste vide, jamais 0 (ADR-0029).
    """

    __tablename__ = "team_match_stats_external"
    __table_args__ = (
        UniqueConstraint("source", "team_match_id", name="uq_team_match_stats_external"),
        CheckConstraint("source IN ('football_data')", name="ck_team_match_stats_external_source"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    team_match_id: Mapped[int] = mapped_column(ForeignKey("staging.team_match.id"), nullable=False, index=True)
    shots: Mapped[int | None] = mapped_column(SmallInteger)
    shots_on_target: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lineup(Base):
    __tablename__ = "lineup"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", "player_id", name="uq_lineup"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False, index=True)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False)
    position: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    shirt_number: Mapped[int | None] = mapped_column(SmallInteger)  # migration 0004
    grid: Mapped[str | None] = mapped_column(Text)
    position_bucket: Mapped[str | None] = mapped_column(position_bucket_enum)


class PlayerMatchStats(Base):
    __tablename__ = "player_match_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_player_match_stats"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False, index=True)

    minutes: Mapped[int | None] = mapped_column(SmallInteger)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1))
    position_bucket: Mapped[str | None] = mapped_column(position_bucket_enum)

    goals: Mapped[int | None] = mapped_column(SmallInteger)
    assists: Mapped[int | None] = mapped_column(SmallInteger)
    shots: Mapped[int | None] = mapped_column(SmallInteger)
    shots_on_target: Mapped[int | None] = mapped_column(SmallInteger)

    key_passes: Mapped[int | None] = mapped_column(SmallInteger)
    pass_accuracy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))

    tackles: Mapped[int | None] = mapped_column(SmallInteger)
    interceptions: Mapped[int | None] = mapped_column(SmallInteger)
    duels_total: Mapped[int | None] = mapped_column(SmallInteger)
    duels_won: Mapped[int | None] = mapped_column(SmallInteger)

    dribbles_attempts: Mapped[int | None] = mapped_column(SmallInteger)
    dribbles_success: Mapped[int | None] = mapped_column(SmallInteger)
    dribbled_past: Mapped[int | None] = mapped_column(SmallInteger)

    fouls_drawn: Mapped[int | None] = mapped_column(SmallInteger)
    fouls_committed: Mapped[int | None] = mapped_column(SmallInteger)
    yellow_cards: Mapped[int | None] = mapped_column(SmallInteger)
    red_cards: Mapped[int | None] = mapped_column(SmallInteger)

    # Remplis a posteriori par understat_player.py, NULL tant qu'Understat
    # n'a pas encore été ingéré pour ce match (cf. prochaine_etape_clustering_mvs.md §2)
    xg: Mapped[float | None] = mapped_column(Numeric(4, 2))
    xa: Mapped[float | None] = mapped_column(Numeric(4, 2))
    npxg: Mapped[float | None] = mapped_column(Numeric(4, 2))

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    shirt_number: Mapped[int | None] = mapped_column(SmallInteger)  # migration 0004
    substitute: Mapped[bool | None] = mapped_column(Boolean)
    captain: Mapped[bool | None] = mapped_column(Boolean)


class PlayerInjury(Base):
    __tablename__ = "player_injury"
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False, index=True)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date | None] = mapped_column(Date)  # NULL tant que le joueur n'a pas repris
    injury_type: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# raw
# ---------------------------------------------------------------------------


class SourceIngestionLog(Base):
    __tablename__ = "source_ingestion_log"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)


class FootballDataMatch(Base):
    __tablename__ = "football_data_match"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_id: Mapped[int] = mapped_column(ForeignKey("raw.source_ingestion_log.id"), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnderstatMatchStats(Base):
    __tablename__ = "understat_match_stats"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_id: Mapped[int] = mapped_column(ForeignKey("raw.source_ingestion_log.id"), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiFootballFixtureDetail(Base):
    __tablename__ = "api_football_fixture_detail"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_id: Mapped[int] = mapped_column(ForeignKey("raw.source_ingestion_log.id"), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnderstatPlayerMatch(Base):
    __tablename__ = "understat_player_match"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_id: Mapped[int] = mapped_column(ForeignKey("raw.source_ingestion_log.id"), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiFootballInjuries(Base):
    """Capturée mais pas encore consommée en staging (cf. recap_etape3, section 7)."""

    __tablename__ = "api_football_injuries"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_id: Mapped[int] = mapped_column(ForeignKey("raw.source_ingestion_log.id"), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------


class TeamMatchFeatures(Base):
    __tablename__ = "team_match_features"
    __table_args__ = (
        UniqueConstraint("team_match_id", name="uq_team_match_features"),
        {"schema": "features"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    team_match_id: Mapped[int] = mapped_column(ForeignKey("staging.team_match.id"), nullable=False)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Forme récente (10 derniers matchs, même contexte domicile/extérieur, toutes compétitions)
    form_points_last10: Mapped[int | None] = mapped_column(SmallInteger)
    form_matches_count: Mapped[int | None] = mapped_column(SmallInteger)

    # Buts (même fenêtre/contexte que la forme)
    goals_for_last10: Mapped[float | None] = mapped_column(Numeric(4, 2))
    goals_against_last10: Mapped[float | None] = mapped_column(Numeric(4, 2))

    # xG (5 derniers matchs, même contexte domicile/extérieur)
    xg_for_last5: Mapped[float | None] = mapped_column(Numeric(4, 2))
    xg_against_last5: Mapped[float | None] = mapped_column(Numeric(4, 2))
    xg_matches_count_last5: Mapped[int | None] = mapped_column(SmallInteger)

    # Classement (snapshot avant match)
    standing_position: Mapped[int | None] = mapped_column(SmallInteger)
    standing_points: Mapped[int | None] = mapped_column(SmallInteger)
    standing_goal_diff: Mapped[int | None] = mapped_column(SmallInteger)

    # Effectif
    squad_avg_age: Mapped[float | None] = mapped_column(Numeric(4, 2))
    squad_stability_score_season: Mapped[float | None] = mapped_column(Numeric(5, 4))


class PlayerStyleProfile(Base):
    __tablename__ = "player_style_profile"
    __table_args__ = (
        UniqueConstraint("player_id", "as_of_date", name="uq_player_style_profile"),
        {"schema": "features"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False)
    as_of_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    position_bucket: Mapped[str] = mapped_column(position_bucket_enum, nullable=False)
    cluster_id: Mapped[int | None] = mapped_column(SmallInteger)  # NULL possible : bruit HDBSCAN
    cluster_label: Mapped[str | None] = mapped_column(Text)  # assigné manuellement après coup
    matches_in_window: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # <= 50
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayerMarketValueScore(Base):
    __tablename__ = "player_market_value_score"
    __table_args__ = (
        UniqueConstraint("player_id", "as_of_date", name="uq_player_market_value_score"),
        {"schema": "features"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False)
    as_of_date: Mapped[dt.date] = mapped_column(Date, nullable=False)

    performance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    potential_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    reputation_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    league_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    availability_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    experience_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    mvs_total: Mapped[float | None] = mapped_column(Numeric(5, 2))  # 0-100

    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# ops (migration 0004)
# ---------------------------------------------------------------------------


class LoadRun(Base):
    """Une exécution de `load` : quand, quel code, quels journaux lus, quels décomptes."""

    __tablename__ = "load_run"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'failed')", name="ck_load_run_status"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    git_commit: Mapped[str | None] = mapped_column(Text)
    raw_dir: Mapped[str] = mapped_column(Text, nullable=False)
    external_raw_dir: Mapped[str | None] = mapped_column(Text)
    manifests: Mapped[dict] = mapped_column(JSONB, nullable=False)  # journal lu -> sha256
    counts: Mapped[dict | None] = mapped_column(JSONB)  # décomptes par table et par motif
    fingerprints: Mapped[dict | None] = mapped_column(JSONB)  # empreinte md5 de chaque table
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 1))


# ---------------------------------------------------------------------------
# features : traçabilité des jeux de données (migration 0006, ADR-0030)
# ---------------------------------------------------------------------------


class DatasetVersion(Base):
    """Une version construite du jeu de données (instantané Parquet dans data/datasets/<version>/).

    Aucune clé étrangère vers `staging` : la trace survit à un `load`, qui vide `staging`.
    """

    __tablename__ = "dataset_version"
    __table_args__ = (UniqueConstraint("version", name="uq_dataset_version_version"), {"schema": "features"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    git_commit: Mapped[str | None] = mapped_column(Text)
    alembic_revision: Mapped[str] = mapped_column(Text, nullable=False)
    load_run_id: Mapped[int | None] = mapped_column(ForeignKey("ops.load_run.id"))
    registry_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
