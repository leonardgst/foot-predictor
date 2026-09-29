"""Réglage reproductible des paramètres de l'Elo (ADR-0031).

    uv run python -m foot_predictor.features.elo_tuning

Grille fixée avant tout calcul, évaluée sur les saisons **2005-06 à 2014-15 seulement** :
2000-01 à 2004-05 amorcent les notes, et l'apprentissage des modèles commence en 2015-16
(ADR-0012). Aucun pli de validation (2021-22 à 2024-25) n'est lu : le calcul s'arrête à la
saison 2014-15.

Critère : log-loss du 1N2 issu de la note, sur les matchs de championnat du top 5 (population
d'évaluation, ADR-0012). Le 1N2 vient d'une régression logistique ordonnée sur
x = (R_dom + H − R_ext) / 400, ajustée sur la même fenêtre (3 paramètres : pente, deux seuils) :

    P(extérieur) = σ(c₁ − β·x),  P(nul) = σ(c₂ − β·x) − σ(c₁ − β·x),  P(domicile) = 1 − σ(c₂ − β·x).

Sorties : `features/params/elo.json` (paramètres figés) et `reports/variables/elo_reglage.md`
(chiffres seulement).
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from foot_predictor.features.elo import EloParams, compute_elo
from foot_predictor.features.leagues import LADDERS, TOP5

GRID = {
    "k": [10, 15, 20, 25, 30, 40],
    "home_advantage": [40, 60, 80, 100],
    "season_regression": [0.0, 0.1, 0.2, 0.33],
    "goal_multiplier": [False, True],
    "initial_gap": [0, 100, 200],
}
WINDOW = range(2005, 2015)  # 2005-06 à 2014-15
LAST_SEASON_READ = 2014

REPO_ROOT = Path(__file__).resolve().parents[3]
PARAMS_PATH = Path(__file__).resolve().parent / "params" / "elo.json"
REPORT_PATH = REPO_ROOT / "reports" / "variables" / "elo_reglage.md"


def outcomes(home_goals: np.ndarray, away_goals: np.ndarray) -> np.ndarray:
    """0 = victoire extérieure, 1 = nul, 2 = victoire à domicile."""
    return np.where(home_goals > away_goals, 2, np.where(home_goals == away_goals, 1, 0))


def ordered_logit_log_loss(x: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    """Ajuste la logistique ordonnée et renvoie (log-loss moyen, paramètres β, c₁, c₂)."""

    def nll(theta: np.ndarray) -> float:
        beta, c1, log_gap = theta
        c2 = c1 + np.exp(log_gap)
        p_away = expit(c1 - beta * x)
        p_not_home = expit(c2 - beta * x)
        p = np.choose(y, [p_away, p_not_home - p_away, 1.0 - p_not_home])
        return float(-np.mean(np.log(np.clip(p, 1e-12, 1.0))))

    fit = minimize(nll, x0=np.array([1.0, -0.6, np.log(1.0)]), method="BFGS")
    beta, c1, log_gap = fit.x
    return fit.fun, np.array([beta, c1, c1 + np.exp(log_gap)])


def evaluation_rows(matches: pd.DataFrame) -> pd.DataFrame:
    """Matchs de saison régulière du top 5, terminés, non exclus, de la fenêtre de réglage."""
    regular = matches["round"].isna() | matches["round"].fillna("").str.startswith("Regular Season")
    return matches[
        matches["api_league_id"].isin(list(TOP5))
        & matches["season_year"].isin(list(WINDOW))
        & regular
        & (matches["status"] == "played")
        & ~matches["excluded"].astype(bool)
        & matches["home_goals_90"].notna()
        & matches["away_goals_90"].notna()
    ]


def score(matches: pd.DataFrame, params: EloParams, evaluation: pd.DataFrame) -> float:
    elo = compute_elo(matches, params)
    home = elo[elo["is_home"]].set_index("match_id")
    rows = home.loc[evaluation["match_id"].to_numpy()]
    x = (rows["elo_pre"].to_numpy(float) + params.home_advantage - rows["opp_elo_pre"].to_numpy(float)) / 400.0
    y = outcomes(evaluation["home_goals_90"].to_numpy(int), evaluation["away_goals_90"].to_numpy(int))
    return ordered_logit_log_loss(x, y)[0]


def tune(matches: pd.DataFrame) -> pd.DataFrame:
    """Évalue toute la grille ; renvoie une ligne par combinaison, triée par log-loss."""
    if matches["season_year"].max() > LAST_SEASON_READ:
        raise ValueError("Le réglage de l'Elo ne lit aucune saison après 2014-15.")
    evaluation = evaluation_rows(matches)
    results = []
    keys = list(GRID)
    for values in itertools.product(*(GRID[k] for k in keys)):
        params = EloParams(**dict(zip(keys, values)))
        results.append({**dict(zip(keys, values)), "log_loss": score(matches, params, evaluation)})
    return pd.DataFrame(results).sort_values("log_loss", kind="mergesort").reset_index(drop=True)


def baseline_log_loss(evaluation: pd.DataFrame) -> float:
    """Référence sans note : fréquences observées de 1, N, 2 sur la fenêtre."""
    y = outcomes(evaluation["home_goals_90"].to_numpy(int), evaluation["away_goals_90"].to_numpy(int))
    freq = np.bincount(y, minlength=3) / len(y)
    return float(-np.mean(np.log(freq[y])))


def render(results: pd.DataFrame, baseline: float, n_matches: int, seconds: float, today: dt.date) -> str:
    best = results.iloc[0]
    lines = [
        f"# Réglage de l'Elo — {today.isoformat()}",
        "",
        "Produit par `python -m foot_predictor.features.elo_tuning` (ADR-0031). Chiffres seulement.",
        "",
        f"- Fenêtre d'évaluation : saisons 2005-06 à 2014-15, matchs de saison régulière du top 5 : **{n_matches}** matchs. "
        "Amorçage depuis 2000-01 ; aucune saison après 2014-15 n'est lue.",
        f"- Grille : {len(results)} combinaisons ("
        + ", ".join(f"`{k}` ∈ {{{', '.join(str(v) for v in vals)}}}" for k, vals in GRID.items())
        + f") ; durée {seconds:.0f} s.",
        "- Critère : log-loss du 1N2 d'une logistique ordonnée sur (R_dom + H − R_ext) / 400, ajustée sur la fenêtre.",
        f"- Référence sans note (fréquences de 1, N, 2) : **{baseline:.4f}**.",
        f"- Meilleure combinaison : **{best['log_loss']:.4f}** (gain {baseline - best['log_loss']:.4f}).",
        "",
        "## 15 meilleures combinaisons",
        "",
        "| Rang | K | H | r | Multiplicateur | Δ | Log-loss |",
        "|---|---|---|---|---|---|---|",
    ]
    for rank, row in results.head(15).iterrows():
        lines.append(
            f"| {rank + 1} | {row['k']} | {row['home_advantage']} | {row['season_regression']} | "
            f"{'oui' if row['goal_multiplier'] else 'non'} | {row['initial_gap']} | {row['log_loss']:.4f} |"
        )
    lines += ["", "## Sensibilité (meilleure log-loss par valeur, les autres paramètres libres)", ""]
    for key in GRID:
        best_by = results.groupby(key)["log_loss"].min()
        lines.append(f"- `{key}` : " + " ; ".join(f"{v} → {ll:.4f}" for v, ll in best_by.items()))
    worst = results.iloc[-1]
    lines += ["", f"Écart entre la meilleure et la pire combinaison : {worst['log_loss'] - best['log_loss']:.4f}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from foot_predictor.features.sources import load_matches

    started = time.monotonic()
    matches = load_matches(kinds=["league"], until=dt.date(LAST_SEASON_READ + 1, 7, 1))
    matches = matches[matches["api_league_id"].isin(list(LADDERS))]
    matches = matches[matches["season_year"] <= LAST_SEASON_READ]
    results = tune(matches)
    seconds = time.monotonic() - started
    evaluation = evaluation_rows(matches)
    best = results.iloc[0]
    params = EloParams(
        k=float(best["k"]),
        home_advantage=float(best["home_advantage"]),
        season_regression=float(best["season_regression"]),
        goal_multiplier=bool(best["goal_multiplier"]),
        initial_gap=float(best["initial_gap"]),
    )
    today = dt.datetime.now(dt.UTC).date()
    PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_PATH.write_text(
        json.dumps(
            {
                "params": params.to_dict(),
                "tuning": {
                    "date": today.isoformat(),
                    "window": "2005-06 à 2014-15, top 5, saison régulière",
                    "matches": int(len(evaluation)),
                    "log_loss_1n2": round(float(best["log_loss"]), 6),
                    "baseline_log_loss": round(baseline_log_loss(evaluation), 6),
                    "grid": GRID,
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        render(results, baseline_log_loss(evaluation), len(evaluation), seconds, today), encoding="utf-8"
    )
    print(f"Paramètres figés : {PARAMS_PATH}\nRapport : {REPORT_PATH}\nMeilleure log-loss : {best['log_loss']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
