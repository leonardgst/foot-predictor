"""Évalue si une recalibration post-hoc (Platt scaling / isotonic regression)
du Modèle A améliore mesurablement la calibration 1N2 -- cf.
`docs/RESULTATS_MODELE.md` section 5 et `modeling/calibration.py` pour les
fonctions réutilisables.

Protocole anti-fuite (même esprit que `run_comparison.py::_select_xi`) :

1. Reproduit exactement la construction du Modèle A de `run_comparison.py` :
   `build_dataset` -> `chronological_split(CUTOFF_DATE)` -> `fit_poisson_model`
   sur TOUT le train set (c'est ce modèle, `poisson_model`, qui sert à prédire
   le test set final -- jamais un modèle réduit).
2. Découpe une fenêtre de calibration À L'INTÉRIEUR du train set (jamais le
   test set) : `val_cutoff = CUTOFF_DATE - 365 jours`, un Poisson RÉDUIT est
   ajusté sur les matchs avant `val_cutoff`, puis utilisé pour prédire la
   fenêtre `[val_cutoff, CUTOFF_DATE)`. Les calibrateurs (Platt, isotonic)
   sont ajustés sur les (probabilité prédite, issue réelle) de cette fenêtre.
3. Les calibrateurs ainsi ajustés sont appliqués aux prédictions du modèle
   `poisson_model` (train complet, étape 1) sur le VRAI test set, jamais
   modifié ni utilisé pour choisir quoi que ce soit en amont.

Simplification documentée : recalibration one-vs-rest + renormalisation
(cf. docstring de `calibration.py`) -- pas une calibration multi-classe
rigoureuse (Dirichlet calibration serait plus correcte, hors scope ici).

Lancement : APP_ENV=dev uv run python -m foot_predictor.modeling.run_calibration_analysis
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.db.session import get_session
from foot_predictor.modeling.calibration import (
    AWAY,
    DRAW,
    HOME,
    calibrate_ovr_and_renormalize,
    fit_ovr_calibrators,
)
from foot_predictor.modeling.dataset import build_dataset
from foot_predictor.modeling.evaluation import (
    MatchPredictions,
    brier_score_1x2,
    calibration_table_home_win,
    compute_predictions,
    independent_poisson_matrix,
    outcome_probabilities,
    to_match_level,
)
from foot_predictor.modeling.poisson_model import fit_poisson_model
from foot_predictor.modeling.split import chronological_split

CUTOFF_DATE = dt.datetime(2024, 8, 1, tzinfo=dt.timezone.utc)

RESULTS_JSON_PATH = Path("docs/model_results.json")


def _extract_outcome_arrays(
    predictions: MatchPredictions,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Dérive, pour chaque match, (p_home, p_draw, p_away) via
    `outcome_probabilities` et l'issue réelle codée HOME=0/DRAW=1/AWAY=2
    (convention de `calibration.py`)."""
    p_home, p_draw, p_away, y_outcome = [], [], [], []
    for row, matrix in zip(predictions.matches.itertuples(), predictions.matrices):
        ph, pd_, pa = outcome_probabilities(matrix)
        p_home.append(ph)
        p_draw.append(pd_)
        p_away.append(pa)
        if row.y_home > row.y_away:
            y_outcome.append(HOME)
        elif row.y_home == row.y_away:
            y_outcome.append(DRAW)
        else:
            y_outcome.append(AWAY)
    return np.array(p_home), np.array(p_draw), np.array(p_away), np.array(y_outcome)


def _brier_score_from_probs(p_home: np.ndarray, p_draw: np.ndarray, p_away: np.ndarray, y_outcome: np.ndarray) -> float:
    onehot = np.zeros((len(y_outcome), 3))
    onehot[np.arange(len(y_outcome)), y_outcome] = 1.0
    probs = np.stack([p_home, p_draw, p_away], axis=1)
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def _calibration_table_from_probs(p_pred: np.ndarray, actual: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Même logique de binning que `evaluation.calibration_table_home_win`,
    appliquée à des tableaux nus (les probabilités recalibrées ne sont plus
    portées par une matrice jointe -- juste 3 scalaires par match)."""
    df = pd.DataFrame({"p_pred": p_pred, "actual": actual})
    df["bin"] = pd.cut(df["p_pred"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True)
    table = (
        df.groupby("bin", observed=True)
        .agg(n=("actual", "size"), mean_predicted=("p_pred", "mean"), observed_frequency=("actual", "mean"))
        .reset_index()
    )
    return table


def main() -> None:
    with get_session() as session:
        print("Construction du dataset (X, y) depuis features.team_match_features...")
        dataset = build_dataset(session)
        split = chronological_split(dataset, CUTOFF_DATE)
        print(f"Split chronologique : cutoff = {CUTOFF_DATE.date()}")
        print(f"  train : {len(split.X_train)} lignes, test : {len(split.X_test)} lignes")

        # --- Étape 1 : Modèle A, exactement comme run_comparison.py -----------
        print("\n=== Modèle A (train complet) ===")
        poisson_model = fit_poisson_model(split.X_train, split.y_train)

        # --- Étape 2 : fenêtre de calibration interne au train set ------------
        val_cutoff = CUTOFF_DATE - dt.timedelta(days=365)
        print(f"\nFenêtre de calibration interne au train (cutoff validation = {val_cutoff.date()}) :")
        fit_mask = split.meta_train["match_date"] < val_cutoff
        val_mask = ~fit_mask
        print(f"  fit (< cutoff validation) : {int(fit_mask.sum())} lignes")
        print(f"  calibration (>= cutoff validation, < {CUTOFF_DATE.date()}) : {int(val_mask.sum())} lignes")

        reduced_model = fit_poisson_model(
            split.X_train.loc[fit_mask].reset_index(drop=True),
            split.y_train.loc[fit_mask].reset_index(drop=True),
        )
        lambda_val = reduced_model.predict_lambda(split.X_train.loc[val_mask].reset_index(drop=True))
        matches_val = to_match_level(
            split.meta_train.loc[val_mask].reset_index(drop=True),
            split.y_train.loc[val_mask].reset_index(drop=True),
            lambda_val,
        )
        predictions_val = compute_predictions(matches_val, independent_poisson_matrix)
        p_home_val, p_draw_val, p_away_val, y_outcome_val = _extract_outcome_arrays(predictions_val)
        print(f"  matchs de calibration (après regroupement par match) : {len(y_outcome_val)}")

        # --- Étape 3 : prédictions du Modèle A (train complet) sur le TEST set -
        print("\n=== Application au test set (jamais touché avant cette étape) ===")
        lambda_test = poisson_model.predict_lambda(split.X_test)
        matches_test = to_match_level(split.meta_test, split.y_test, lambda_test)
        predictions_test = compute_predictions(matches_test, independent_poisson_matrix)
        p_home_test, p_draw_test, p_away_test, y_outcome_test = _extract_outcome_arrays(predictions_test)

        brier_before = brier_score_1x2(predictions_test)
        calib_table_before = calibration_table_home_win(predictions_test)
        print(f"Avant recalibration -- Brier 1N2 (test) : {brier_before:.4f}")
        print(calib_table_before)

        results: dict = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cutoff_date": CUTOFF_DATE.isoformat(),
            "val_cutoff": val_cutoff.isoformat(),
            "n_calibration_fit_rows": int(fit_mask.sum()),
            "n_calibration_window_rows": int(val_mask.sum()),
            "n_calibration_window_matches": int(len(y_outcome_val)),
            "n_test_matches": int(len(y_outcome_test)),
            "before": {
                "brier_score_1x2": brier_before,
                "calibration_home_win": calib_table_before.to_dict(orient="records"),
            },
        }

        for method in ("platt", "isotonic"):
            print(f"\n=== Recalibration : {method} ===")
            calibrators = fit_ovr_calibrators(method, p_home_val, p_draw_val, p_away_val, y_outcome_val)
            p_home_c, p_draw_c, p_away_c = calibrate_ovr_and_renormalize(
                calibrators, p_home_test, p_draw_test, p_away_test
            )

            brier_after = _brier_score_from_probs(p_home_c, p_draw_c, p_away_c, y_outcome_test)
            calib_table_after = _calibration_table_from_probs(p_home_c, (y_outcome_test == HOME).astype(int))
            print(f"Après recalibration ({method}) -- Brier 1N2 (test) : {brier_after:.4f}")
            print(calib_table_after)

            results[method] = {
                "brier_score_1x2": brier_after,
                "delta_brier_before_minus_after": brier_before - brier_after,
                "calibration_home_win": calib_table_after.to_dict(orient="records"),
            }

        # --- Persistance : fusion dans docs/model_results.json existant -------
        existing = {}
        if RESULTS_JSON_PATH.exists():
            existing = json.loads(RESULTS_JSON_PATH.read_text(encoding="utf-8"))
        existing["calibration_experiment"] = results
        RESULTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON_PATH.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
        print(f"\nRésultats de l'expérience de calibration écrits dans {RESULTS_JSON_PATH} (clé 'calibration_experiment')")


if __name__ == "__main__":
    main()
