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
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
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
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompetitionSourceMapping(Base):
    __tablename__ = "competition_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_competition_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("staging.competition.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class Season(Base):
    __tablename__ = "season"
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("staging.competition.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)


class Team(Base):
    __tablename__ = "team"
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamSourceMapping(Base):
    __tablename__ = "team_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_team_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class Player(Base):
    __tablename__ = "player"
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
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
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)


class Match(Base):
    __tablename__ = "match"
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("staging.competition.id"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("staging.season.id"), nullable=False)
    match_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)
    home_goals: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(match_status_enum, nullable=False, server_default="scheduled")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchSourceMapping(Base):
    __tablename__ = "match_source_mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "source_ref", name="uq_match_source_mapping"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
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
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    goals_for: Mapped[int | None] = mapped_column(SmallInteger)
    goals_against: Mapped[int | None] = mapped_column(SmallInteger)
    xg_for: Mapped[float | None] = mapped_column(Numeric(4, 2))
    xg_against: Mapped[float | None] = mapped_column(Numeric(4, 2))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lineup(Base):
    __tablename__ = "lineup"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", "player_id", name="uq_lineup"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False)
    position: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayerMatchStats(Base):
    __tablename__ = "player_match_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_player_match_stats"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("staging.match.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("staging.team.id"), nullable=False)

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


class PlayerInjury(Base):
    __tablename__ = "player_injury"
    __table_args__ = {"schema": "staging"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("staging.player.id"), nullable=False)
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
    cluster_label: Mapped[str | None] = mapped_column(Text)       # assigné manuellement après coup
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