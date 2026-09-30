"""Références B0 et B1 (rapport I.4, étape M0) : « quel est le niveau zéro ? ».

- **B0** : chaque équipe marque selon une loi de Poisson de moyenne μ, la moyenne des buts par
  équipe et par match sur toutes les lignes d'apprentissage. Le total suit donc
  Poisson(2μ), le même pour tous les matchs. Aucune variable.
- **B1** : moyenne par championnat et par côté (domicile, extérieur), sur les `window`
  saisons d'apprentissage les plus récentes : λ_dom = moyenne des buts à domicile dans le
  championnat du match, λ_ext de même à l'extérieur ; total Poisson(λ_dom + λ_ext). La
  fenêtre se choisit par validation interne (hyperparamètre).

Ce que B1 apprend en plus de B0 : l'avantage du terrain et le niveau de buts propre à chaque
championnat (la Bundesliga marque plus que la Liga, par exemple), éventuellement sa tendance
récente (fenêtre courte).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.modeling.models.base import MatchPredictions, Model, match_frame


class B0(Model):
    """Poisson de moyenne globale : λ_dom = λ_ext = μ (moyenne des buts par ligne d'apprentissage)."""

    name = "B0"

    def fit(self, rows: pd.DataFrame) -> B0:
        self.mu_ = float(rows["goals_for"].mean())
        return self

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        matches = match_frame(rows)
        lam = np.full(len(matches), self.mu_)
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), lam, lam)


class B1(Model):
    """Moyenne par championnat et par côté, sur les `window` dernières saisons d'apprentissage."""

    name = "B1"
    GRID = {"window": [1, 2, 3, 6]}

    def __init__(self, window: int = 3) -> None:
        if int(window) < 1:
            raise ValueError(f"B1 : fenêtre de {window} saison(s), au moins 1 attendue.")
        super().__init__(window=window)
        self.window = int(window)

    def fit(self, rows: pd.DataFrame) -> B1:
        last = int(rows["season_year"].max())
        recent = rows[rows["season_year"] > last - self.window]
        self.means_ = recent.groupby(["api_league_id", "is_home"])["goals_for"].mean().to_dict()
        return self

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        matches = match_frame(rows)
        league = matches["home_api_league_id"].to_numpy()
        lambda_home = np.array([self.means_.get((lg, True), np.nan) for lg in league])
        lambda_away = np.array([self.means_.get((lg, False), np.nan) for lg in league])
        known = ~(np.isnan(lambda_home) | np.isnan(lambda_away))  # championnat absent de l'apprentissage
        return MatchPredictions.independent_poisson(
            matches.index.to_numpy()[known], lambda_home[known], lambda_away[known]
        )
