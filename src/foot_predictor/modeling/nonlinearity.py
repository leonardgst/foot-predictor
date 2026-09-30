"""Diagnostic de non-linéarité (sous-étape 4.10) : faut-il des splines sur l'Elo ?

M3 suppose log λ linéaire dans l'Elo (standardisé) de l'équipe et de l'adversaire. Si la vraie
relation est courbe, les buts observés s'écartent des buts attendus de façon **systématique**
selon l'écart d'Elo. On le mesure sur les lignes (match, équipe) d'apprentissage :

- classes d'effectifs égaux de `elo_diff` (déciles) ;
- par classe : O = Σ y, E = Σ λ̂, rapport O/E et z = (O − E) / √E ;
- statistique Σ z² : sous un modèle bien spécifié, approximativement χ² à (classes − 1) degrés
  de liberté (une contrainte : Σ (O − E) ≈ 0 par les équations du score).

Des splines ne se justifient que si le test rejette **et** que l'écart a une forme lisible
(par exemple O/E croissant aux extrémités). Pour ne rien apprendre des saisons de test, le
diagnostic n'utilise que 2015-16 à 2020-21 (apprentissage du premier pli, jamais testé).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2

from foot_predictor.features.leagues import TOP5
from foot_predictor.modeling.models.team import M3

DIAGNOSTIC_SEASONS = range(2015, 2021)


def observed_expected_by_bin(values, goals, lam, n_bins: int = 10) -> tuple[pd.DataFrame, dict]:
    """Tableau O/E par classe d'effectifs égaux de `values`, et test Σ z² ~ χ²(classes − 1)."""
    frame = pd.DataFrame({"x": np.asarray(values, float), "y": np.asarray(goals, float), "mu": np.asarray(lam)})
    frame["bin"] = pd.qcut(frame["x"].rank(method="first"), n_bins, labels=False)
    table = frame.groupby("bin").agg(
        n=("y", "size"), x_mean=("x", "mean"), observed=("y", "sum"), expected=("mu", "sum")
    )
    table["ratio"] = table["observed"] / table["expected"]
    table["z"] = (table["observed"] - table["expected"]) / np.sqrt(table["expected"])
    statistic = float((table["z"] ** 2).sum())
    return table.reset_index(), {
        "statistic": statistic,
        "df": n_bins - 1,
        "p_value": float(chi2.sf(statistic, n_bins - 1)),
    }


def elo_nonlinearity(data: pd.DataFrame, n_bins: int = 10) -> tuple[pd.DataFrame, dict]:
    """M3 (G0 + G1) ajusté sur 2015-16 à 2020-21 (top 5), résidus par décile de `elo_diff`, en échantillon."""
    rows = data[data["season_year"].isin(list(DIAGNOSTIC_SEASONS)) & data["api_league_id"].isin(list(TOP5))]
    model = M3(("G0", "G1")).fit(rows)
    return observed_expected_by_bin(rows["elo_diff"], rows["goals_for"], model.team_lambda(rows), n_bins)


def render(table: pd.DataFrame, test: dict) -> str:
    lines = [
        "| Décile de l'écart d'Elo | Lignes | Écart d'Elo moyen | Buts observés | Buts attendus (M3) | O/E | z |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, row in table.iterrows():
        lines.append(
            f"| {int(row['bin']) + 1} | {int(row['n'])} | {row['x_mean']:+.0f} | {row['observed']:.0f} "
            f"| {row['expected']:.1f} | {row['ratio']:.3f} | {row['z']:+.2f} |"
        )
    lines += ["", f"Σ z² = {test['statistic']:.2f}, {test['df']} degrés de liberté, p = {test['p_value']:.3f}."]
    return "\n".join(lines) + "\n"
