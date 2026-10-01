"""Schémas Pydantic de l'API (contrat du rapport F.6, ADR-0040) : ce qui entre et ce qui sort.

FastAPI s'en sert pour **valider** chaque réponse (un champ manquant ou d'un mauvais type est une
erreur du serveur, pas une réponse fausse) et pour produire la documentation OpenAPI (`/docs`).
Aucun schéma ne contient de chemin de fichier, d'URL de base ni de secret.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["replay", "live"]
Horizon = Literal["H1", "H2"]
Status = Literal["available", "unavailable", "out_of_scope", "excluded", "h2_unavailable"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: str
    model: str | None = Field(description="version du modèle actif chargé, ou la raison de son absence")
    data_version: str | None = None


class Competition(BaseModel):
    id: int
    name: str | None
    api_league_id: int | None
    country: str | None
    kind: str | None
    in_model_scope: bool = Field(description="vrai pour un championnat du top 5 (périmètre du modèle H1)")


class VariableStatus(BaseModel):
    variable: str
    side: Literal["domicile", "exterieur"]
    status: Literal["presente", "manquante", "perimee"]
    value: float | int | None = None
    reason: str | None = None
    source_date: str | None = None


class Interval(BaseModel):
    low: int
    high: int
    high_label: str = Field(description="« 10+ » quand la borne haute est la case « 10 et plus »")
    announced_coverage: float = Field(description="P̂(T ∈ [low ; high]) : la couverture annoncée (ADR-0009)")


class PredictionValues(BaseModel):
    lambda_home: float
    lambda_away: float
    expected_total: float
    total_distribution: dict[str, float] = Field(description="P(T = k) pour k de 0 à 9 et « 10+ »")
    p_over_2_5: float
    interval: Interval


class Score(BaseModel):
    home: int | None
    away: int | None


class MarketReference(BaseModel):
    p_over_2_5: float
    odds_column: str | None = None
    version: str


class MatchSummary(BaseModel):
    match_id: int
    date: dt.date
    kickoff_utc: str | None
    competition_id: int
    api_league_id: int
    competition: str | None
    season: int
    round: str | None
    home_team_id: int
    away_team_id: int
    home_team: str | None
    away_team: str | None
    mode: Mode
    horizon: Horizon
    status: Status
    reasons: list[str]
    model_version: str
    data_version: str
    data_complete_until: str


class AvailabilityOut(MatchSummary):
    variables: list[VariableStatus]


class PredictionOut(AvailabilityOut):
    prediction: PredictionValues
    actual_score: Score | None = None
    market_reference: MarketReference | None = None
    saved: dict | None = Field(None, description="ligne de ops.prediction : identifiant, créée ou existante, date")


class Problem(BaseModel):
    """Corps des erreurs 403, 404, 409 et 501 : un message et, pour un 409, les raisons."""

    detail: str
    reasons: list[str] = []


class SourceFreshness(BaseModel):
    source: str
    last_update: str | None
    complete_until: str | None
    note: str | None = None


class Freshness(BaseModel):
    data_version: str
    sources: list[SourceFreshness]
