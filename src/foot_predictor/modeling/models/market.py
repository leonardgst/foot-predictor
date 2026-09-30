"""Référence de marché : P(T > 2,5) implicite dans les cotes plus/moins 2,5 de football-data (ADR-0036).

Pour chaque match, avec q₊ = 1 / cote(plus de 2,5) et q₋ = 1 / cote(moins de 2,5) :

    P_marché(T > 2,5) = q₊ / (q₊ + q₋)

La somme q₊ + q₋ dépasse 1 : c'est la marge du bookmaker, retirée ici par **normalisation
proportionnelle** (décision 9). Deux versions :

- `avant_cloture` : référence de l'horizon H1 ;
- `cloture` : **borne haute** (la cote de clôture sait ce que sait le marché au coup d'envoi),
  jamais une variable ni une référence de l'horizon H1.

Le marché ne donne pas de loi complète du total : il n'est évalué que sur l'événement
plus/moins 2,5 (Brier et log-loss binaire), jamais au log-loss du total.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foot_predictor.ingestion.football_data_odds import implied_probability_over


def market_probabilities(odds: pd.DataFrame) -> pd.DataFrame:
    """Ajoute `p_over` (marge retirée) à une table de cotes (colonnes `odds_over_2_5`, `odds_under_2_5`)."""
    odds = odds.copy()
    odds["p_over"] = implied_probability_over(
        odds["odds_over_2_5"].astype(float).to_numpy(), odds["odds_under_2_5"].astype(float).to_numpy()
    )
    return odds


def load_market_probabilities(
    sealed_test: bool = False, experiment: str | None = None, sealed_log=None
) -> pd.DataFrame:
    """Cotes lues par la porte (scellé filtré en SQL ; levé seulement pour le test scellé, journalisé)."""
    from foot_predictor.features.sources import load_odds

    return market_probabilities(load_odds(sealed_test=sealed_test, experiment=experiment, sealed_log=sealed_log))


def probabilities(odds: pd.DataFrame, version: str, match_ids) -> np.ndarray:
    """P_marché(T > 2,5) des `match_ids`, dans leur ordre, pour une version (`avant_cloture`, `cloture`)."""
    table = odds[odds["version"] == version].set_index("match_id")["p_over"]
    return table.loc[np.asarray(match_ids)].to_numpy(dtype=float)
