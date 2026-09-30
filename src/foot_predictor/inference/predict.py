"""Prédiction d'un match ou d'une journée (décisions 5 et 6 de la partie 5 ; rapport F.5 ; ADR-0040).

`predict(match, horizon, date de référence)` :

1. modèle : celui du pli de la saison en rejeu, le modèle actif en live (`inference/models.py`) ;
2. variables : la fonction de l'entraînement, historique tronqué au jour du match (`inference/rows.py`) ;
3. matrice de disponibilité (`inference/availability.py`) ; une variable non présente ⇒ **aucune
   prédiction**, statut et raisons ;
4. sinon : λ domicile et λ extérieur, loi du total P(T = k) pour k de 0 à 9 et « 10 et plus »,
   E[T] = λ_dom + λ_ext, P(T > 2,5) = 1 − P(T ≤ 2), intervalle [q10 ; q90] de la loi discrète
   **avec sa couverture annoncée** P̂(T ∈ [q10 ; q90]) (ADR-0009), variables utilisées et leurs
   valeurs, version du modèle, date des données ;
5. en rejeu, le score réel (avant le 1er juillet 2025 seulement) ; à titre de comparaison, la
   probabilité implicite de plus de 2,5 buts du marché avant clôture (`market_reference`, ADR-0036).

**Scellé** : toute date de référence à partir du 1er juillet 2025 est refusée tant que le test
scellé n'est pas terminé ; le rejeu ne s'ouvre que sur 2021-22 à 2024-25 (ADR-0011, règle 2).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from foot_predictor.inference import models as model_store
from foot_predictor.inference.availability import Freshness, match_availability
from foot_predictor.inference.rows import RowsCache, as_day
from foot_predictor.modeling import metrics
from foot_predictor.seal import SEAL_DATE

MODES = ("replay", "live")
K_LABELS = [str(k) for k in range(10)] + ["10+"]


class ReferenceDateRefused(RuntimeError):
    """Date de référence non ouverte (scellé, saison de rejeu fermée, live dans le passé)."""


@dataclass
class InferenceContext:
    """Tout ce qu'une prédiction lit, chargé une fois (API, commande) : table des matchs, caches, sources."""

    matches: pd.DataFrame
    data_version: str
    freshness: Freshness
    team_names: dict[int, str] = field(default_factory=dict)
    competition_names: dict[int, str] = field(default_factory=dict)
    odds: pd.DataFrame | None = None
    dataset: pd.DataFrame | None = None
    today: dt.date | None = None
    """« Aujourd'hui » : la date du jour, ou une date simulée (tests du live)."""
    sealed_log: object = None
    replay_root: object = None
    active_version: str | None = None
    _rows: RowsCache | None = None
    _models: dict = field(default_factory=dict)

    @property
    def rows_cache(self) -> RowsCache:
        if self._rows is None:
            self._rows = RowsCache(self.matches, self.data_version)
        return self._rows

    def model(self, day: dt.date, mode: str) -> model_store.LoadedModel:
        key = (mode, model_store.season_of(day) if mode == "replay" else "actif")
        if key not in self._models:
            if mode == "replay":
                kwargs = {"log_path": self.sealed_log}
                if self.replay_root is not None:
                    kwargs["replay_root"] = self.replay_root
                self._models[key] = model_store.replay_model(model_store.season_of(day), self.dataset, **kwargs)
            else:
                self._models[key] = model_store.load_active(self.active_version)
        return self._models[key]


def check_reference_date(day: dt.date, mode: str, context: InferenceContext) -> None:
    """Refus explicites (décision 8) : scellé, saison de rejeu non ouverte, live sur un jour passé."""
    if mode not in MODES:
        raise ValueError(f"Mode inconnu : {mode} (attendu : {MODES})")
    if day >= SEAL_DATE and not model_store.sealed_test_done(log_path=context.sealed_log):
        raise ReferenceDateRefused(
            f"{day.isoformat()} : date sous scellés (à partir du {SEAL_DATE.isoformat()}) tant que le test scellé "
            "n'est pas terminé (ADR-0012)."
        )
    if mode == "replay":
        try:
            model_store.check_replay_season(model_store.season_of(day), context.sealed_log)
        except model_store.ModelUnavailable as error:
            raise ReferenceDateRefused(str(error)) from error
    elif context.today is not None and day < context.today:
        raise ReferenceDateRefused(f"{day.isoformat()} : le live ne prédit que des matchs à venir (aujourd'hui : "
                                   f"{context.today.isoformat()}) ; utiliser le rejeu.")  # fmt: skip


def _match_info(match: pd.Series, context: InferenceContext) -> dict:
    kickoff = pd.Timestamp(match["match_date"])
    return {
        "match_id": int(match["match_id"]),
        "date": as_day(match["match_day"]).isoformat(),
        "kickoff_utc": kickoff.isoformat() if match.get("origin") != "hors_api" else None,
        "competition_id": int(match["competition_id"]),
        "api_league_id": int(match["api_league_id"]),
        "competition": context.competition_names.get(int(match["competition_id"])),
        "season": int(match["season_year"]),
        "round": match.get("round") if isinstance(match.get("round"), str) else None,
        "home_team_id": int(match["home_team_id"]),
        "away_team_id": int(match["away_team_id"]),
        "home_team": context.team_names.get(int(match["home_team_id"])),
        "away_team": context.team_names.get(int(match["away_team_id"])),
    }


def distribution_summary(total: np.ndarray) -> dict:
    """Loi du total, P(T > 2,5), intervalle [q10 ; q90] et couverture annoncée (ADR-0009)."""
    probs = np.atleast_2d(total)
    low, high = metrics.prediction_interval(probs)
    coverage = metrics.announced_coverage(probs, low, high)
    return {
        "total_distribution": {label: float(p) for label, p in zip(K_LABELS, probs[0], strict=True)},
        "p_over_2_5": float(1.0 - probs[0, :3].sum()),
        "interval": {
            "low": int(low[0]),
            "high": int(high[0]),
            "high_label": K_LABELS[int(high[0])],
            "announced_coverage": float(coverage[0]),
        },
    }


def _market_reference(match_id: int, match_date: pd.Timestamp, context: InferenceContext) -> dict | None:
    """Probabilité implicite de plus de 2,5 buts avant clôture (ADR-0036), jamais pour un match scellé."""
    if context.odds is None or match_date >= pd.Timestamp(SEAL_DATE, tz="UTC"):
        return None
    odds = context.odds[(context.odds["match_id"] == match_id) & (context.odds["version"] == "avant_cloture")]
    if odds.empty:
        return None
    row = odds.iloc[0]
    return {"p_over_2_5": float(row["p_over"]), "odds_column": row.get("odds_column"), "version": "avant_cloture"}


def predict_match(match: pd.Series, rows: pd.DataFrame, model, context: InferenceContext, mode: str,
                  horizon: str = "H1") -> dict:  # fmt: skip
    """Réponse complète pour un match : informations, disponibilité, prédiction ou raisons."""
    availability = match_availability(match, rows, tuple(model.features), context.freshness, horizon)
    result = {
        **_match_info(match, context),
        "mode": mode,
        "horizon": horizon,
        "status": availability.status,
        "reasons": availability.reasons,
        "availability": availability.to_dict()["variables"],
        "model_version": model.version,
        "data_version": context.data_version,
        "data_complete_until": context.freshness.complete_until.isoformat(),
        "prediction": None,
        "actual_score": None,
        "market_reference": None,
    }
    match_date = pd.Timestamp(match["match_date"])
    if mode == "replay" and match_date < pd.Timestamp(SEAL_DATE, tz="UTC") and match.get("status") == "played":
        result["actual_score"] = {"home": _int(match["home_goals_90"]), "away": _int(match["away_goals_90"])}
    result["market_reference"] = _market_reference(int(match["match_id"]), match_date, context)
    if not availability.is_available:
        return result
    predicted = model.model.predict(rows)
    lambda_home, lambda_away = float(predicted.lambda_home[0]), float(predicted.lambda_away[0])
    result["prediction"] = {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "expected_total": lambda_home + lambda_away,
        **distribution_summary(predicted.total[0]),
    }
    return result


def _int(value):
    return None if pd.isna(value) else int(value)


def predict_day(
    day,
    mode: str,
    context: InferenceContext,
    competition_ids=None,
    match_ids=None,
    horizon: str = "H1",
) -> list[dict]:
    """Toutes les réponses d'un jour (ou d'une sélection), dans l'ordre du coup d'envoi."""
    day = as_day(day)
    check_reference_date(day, mode, context)
    matches = context.matches[context.matches["match_day"] == day]
    if competition_ids is not None:
        matches = matches[matches["competition_id"].isin(list(competition_ids))]
    if match_ids is not None:
        matches = matches[matches["match_id"].isin(list(match_ids))]
    if matches.empty:
        return []
    model = context.model(day, mode)
    day_rows = context.rows_cache.rows(day)
    results = []
    for _, match in matches.sort_values(["match_date", "match_id"]).iterrows():
        rows = day_rows[day_rows["match_id"] == match["match_id"]] if len(day_rows) else day_rows
        results.append(predict_match(match, rows, model, context, mode, horizon))
    return results
