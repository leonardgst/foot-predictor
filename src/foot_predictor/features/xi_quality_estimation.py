"""Estimation unique de la constante de rétrécissement de `xi_quality` (ADR-0013, estimation bayésienne empirique).

    uv run python -m foot_predictor.features.xi_quality_estimation

Modèle : la note d'une apparition de w minutes vaut θ_joueur + bruit de variance σ²/w ; les θ d'un
même poste ont pour variance τ². La note rétrécie d'un joueur à M minutes pèse sa moyenne par
M / (M + k), avec **k = σ² / τ²** (en minutes).

Estimation par la méthode des moments, sur **2015-16 à 2019-20 seulement** : cette période est
dans l'apprentissage des quatre plis (2021-22 à 2024-25), aucune note de validation n'y sert.

- σ² : variance intra-joueur, Σ w (r − r̄_joueur)² / (apparitions − joueurs) ;
- τ² : variance inter-joueurs d'un poste, (Q − (P − 1) σ²) / (W − Σ W_p² / W) avec Q = Σ W_p (r̄_p − r̄)²
  (analyse de variance déséquilibrée), les postes étant poolés. Un joueur a le poste où il a le plus joué.

Résultat figé dans `features/params/xi_quality.json`, rapport chiffré dans `reports/variables/xi_quality.md`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from foot_predictor.features import sources
from foot_predictor.features.leagues import LADDERS
from foot_predictor.features.xi_quality import PARAMS_PATH, rated_appearances

LAST_SEASON = 2019  # 2019-20
FIRST_SEASON = 2015  # 2015-16
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "reports" / "variables" / "xi_quality.md"


def _modal_bucket(appearances: pd.DataFrame) -> pd.Series:
    """Poste où chaque joueur a le plus de minutes notées."""
    minutes = appearances.groupby(["player", "bucket"])["weight"].sum().reset_index()
    return (
        minutes.sort_values(["player", "weight"], ascending=[True, False])
        .drop_duplicates("player")
        .set_index("player")["bucket"]
    )


def estimate_shrinkage(appearances: pd.DataFrame) -> dict:
    """k = σ² / τ² (minutes), avec ses éléments, à partir d'apparitions de `rated_appearances`."""
    used = appearances[(appearances["weight"] > 0) & appearances["bucket"].notna()].copy()
    used["rating"] = used["weighted_rating"] / used["weight"]
    per_player = used.groupby("player").agg(W=("weight", "sum"), WR=("weighted_rating", "sum"), n=("weight", "size"))
    per_player["mean"] = per_player["WR"] / per_player["W"]
    per_player["bucket"] = _modal_bucket(used)
    used = used.join(per_player["mean"].rename("player_mean"), on="player")
    within = float((used["weight"] * (used["rating"] - used["player_mean"]) ** 2).sum())
    sigma2 = within / (len(used) - len(per_player))

    q_total, df_total, scale_total = 0.0, 0, 0.0
    for _, group in per_player.groupby("bucket"):
        total = group["W"].sum()
        centre = (group["W"] * group["mean"]).sum() / total
        q_total += float((group["W"] * (group["mean"] - centre) ** 2).sum())
        df_total += len(group) - 1
        scale_total += float(total - (group["W"] ** 2).sum() / total)
    tau2 = (q_total - df_total * sigma2) / scale_total
    if tau2 <= 0:
        raise ValueError(f"variance inter-joueurs non positive ({tau2:.6f}) : rétrécissement non défini")
    return {
        "shrinkage_minutes": round(sigma2 / tau2, 1),
        "sigma2": round(sigma2, 3),
        "tau2": round(tau2, 4),
        "players": int(len(per_player)),
        "appearances": int(len(used)),
    }


def main() -> int:
    matches = sources.load_matches()
    league = matches[matches["api_league_id"].isin(list(LADDERS))]
    ids = sorted(league["competition_id"].unique().tolist())
    lineups = sources.load_lineups(competition_ids=ids)
    sample = league[(league["season_year"] >= FIRST_SEASON) & (league["season_year"] <= LAST_SEASON)]
    appearances = rated_appearances(sample, lineups)
    result = estimate_shrinkage(appearances)
    result["seasons"] = f"{FIRST_SEASON}-{str(FIRST_SEASON + 1)[2:]} à {LAST_SEASON}-{str(LAST_SEASON + 1)[2:]}"
    PARAMS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Rétrécissement de `xi_quality` (estimation unique)",
        "",
        f"Période d'estimation : {result['seasons']} (jamais au-delà). Chiffres seulement.",
        "",
        "| Quantité | Valeur |",
        "|---|---|",
        f"| Joueurs | {result['players']} |",
        f"| Apparitions notées | {result['appearances']} |",
        f"| σ² intra-joueur (par minute) | {result['sigma2']} |",
        f"| τ² inter-joueurs | {result['tau2']} |",
        f"| **k = σ² / τ² (minutes)** | **{result['shrinkage_minutes']}** |",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
