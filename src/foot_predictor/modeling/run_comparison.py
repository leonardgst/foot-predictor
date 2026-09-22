"""Script de bout en bout : construit (X, y), split chronologique, ajuste le
Modèle A (Poisson indépendant) puis le Modèle B (Dixon-Coles hybride), évalue
les deux sur le même test set et écrit les résultats dans
docs/RESULTATS_MODELE.md + un fichier JSON brut pour réutilisation ultérieure.

Lancement : APP_ENV=dev uv run python -m foot_predictor.modeling.run_comparison
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.db.session import get_session
from foot_predictor.modeling.dataset import build_dataset
from foot_predictor.modeling.dixon_coles import fit_dixon_coles, prepare_match_arrays, tau_correction
from foot_predictor.modeling.evaluation import (
    MAX_GOALS,
    brier_score_1x2,
    calibration_table_home_win,
    compute_predictions,
    dixon_coles_matrix,
    independent_poisson_matrix,
    log_loss_exact_score,
    low_score_bias_table,
    to_match_level,
)
from foot_predictor.modeling.poisson_model import fit_poisson_model
from foot_predictor.modeling.split import chronological_split

# Coupure documentée : dernière saison complète (2024-2025, démarrant en août
# 2024 pour les 5 championnats suivis) en test, tout le reste en train.
CUTOFF_DATE = dt.datetime(2024, 8, 1, tzinfo=dt.timezone.utc)

# Grille de recherche pour xi (vitesse de décroissance temporelle, en 1/jour) --
# sélectionné par validation temporelle interne au train set (jamais sur le
# test set), cf. section 5.2 du document ("hyperparamètre à calibrer").
XI_GRID = [0.0, 0.001, 0.002, 0.005, 0.01]

RESULTS_JSON_PATH = Path("docs/model_results.json")
RESULTS_MD_PATH = Path("docs/RESULTATS_MODELE.md")


def _evaluate(matches: pd.DataFrame, matrix_fn) -> dict:
    predictions = compute_predictions(matches, matrix_fn)
    return {
        "n_matches": len(matches),
        "log_loss_exact_score": log_loss_exact_score(predictions),
        "brier_score_1x2": brier_score_1x2(predictions),
        "calibration_home_win": calibration_table_home_win(predictions).to_dict(orient="records"),
        "low_score_bias": low_score_bias_table(predictions).to_dict(orient="records"),
    }, predictions


def _select_xi(X_train, y_train, meta_train, val_cutoff: dt.datetime) -> tuple[float, list[dict]]:
    """Recherche de xi par validation temporelle À L'INTÉRIEUR du train set :
    on ajuste sur les matchs avant `val_cutoff`, on évalue sur ceux entre
    `val_cutoff` et CUTOFF_DATE (jamais sur le vrai test set)."""
    fit_mask = meta_train["match_date"] < val_cutoff
    val_mask = ~fit_mask

    search_log = []
    best_xi, best_log_loss = None, np.inf
    for xi in XI_GRID:
        model = fit_dixon_coles(
            X_train.loc[fit_mask].reset_index(drop=True),
            y_train.loc[fit_mask].reset_index(drop=True),
            meta_train.loc[fit_mask].reset_index(drop=True),
            xi=xi,
        )
        val_arrays = prepare_match_arrays(
            X_train.loc[val_mask].reset_index(drop=True),
            y_train.loc[val_mask].reset_index(drop=True),
            meta_train.loc[val_mask].reset_index(drop=True),
        )
        lambda_home, lambda_away = model.predict_match_lambdas(val_arrays)
        val_matches = pd.DataFrame(
            {
                "match_id": val_arrays.match_id,
                "lambda_home": lambda_home,
                "lambda_away": lambda_away,
                "y_home": val_arrays.y_home.astype(int),
                "y_away": val_arrays.y_away.astype(int),
            }
        )
        predictions = compute_predictions(
            val_matches, lambda h, a: dixon_coles_matrix(h, a, model.rho, tau_correction)
        )
        loss = log_loss_exact_score(predictions)
        search_log.append({"xi": xi, "val_log_loss": loss})
        print(f"  xi={xi:<7} -> log-loss validation = {loss:.4f}")
        if loss < best_log_loss:
            best_xi, best_log_loss = xi, loss

    return best_xi, search_log


def main() -> None:
    with get_session() as session:
        print("Construction du dataset (X, y) depuis features.team_match_features...")
        dataset = build_dataset(session)
        print(f"  {len(dataset.X)} lignes ({len(dataset.X) // 2} matchs environ)")
        print(f"  matchs écartés (features manquantes d'un côté) : {dataset.n_matches_dropped_missing_features}")
        print(f"  lignes écartées (valeur de feature manquante) : {dataset.n_rows_dropped_missing_values}")

        split = chronological_split(dataset, CUTOFF_DATE)
        print(f"Split chronologique : cutoff = {CUTOFF_DATE.date()}")
        print(f"  train : {len(split.X_train)} lignes, test : {len(split.X_test)} lignes")

        # --- Modèle A -------------------------------------------------------
        print("\n=== Modèle A : Poisson indépendant ===")
        poisson_model = fit_poisson_model(split.X_train, split.y_train)
        print(poisson_model.summary())

        lambda_train_a = poisson_model.predict_lambda(split.X_train)
        lambda_test_a = poisson_model.predict_lambda(split.X_test)
        matches_train_a = to_match_level(split.meta_train, split.y_train, lambda_train_a)
        matches_test_a = to_match_level(split.meta_test, split.y_test, lambda_test_a)

        metrics_a, predictions_a = _evaluate(matches_test_a, independent_poisson_matrix)
        print(f"Modèle A -- log-loss test : {metrics_a['log_loss_exact_score']:.4f}")
        print(f"Modèle A -- Brier 1N2 test : {metrics_a['brier_score_1x2']:.4f}")
        print("Modèle A -- biais scores bas (prédit vs observé) :")
        print(pd.DataFrame(metrics_a["low_score_bias"]))

        # --- Modèle B ---------------------------------------------------------
        print("\n=== Modèle B : Dixon-Coles hybride ===")
        val_cutoff = CUTOFF_DATE - dt.timedelta(days=365)
        print(f"Recherche de xi par validation temporelle interne (cutoff validation = {val_cutoff.date()}) :")
        best_xi, xi_search_log = _select_xi(split.X_train, split.y_train, split.meta_train, val_cutoff)
        print(f"  xi retenu = {best_xi}")

        dc_model = fit_dixon_coles(split.X_train, split.y_train, split.meta_train, xi=best_xi)
        print(f"  gamma (avantage terrain) = {dc_model.gamma:.4f}")
        print(f"  rho (corrélation basse-score) = {dc_model.rho:.4f}")
        print(f"  delta = {dict(zip(dc_model.delta_feature_names, dc_model.delta))}")

        test_arrays = prepare_match_arrays(split.X_test, split.y_test, split.meta_test)
        lambda_home_b, lambda_away_b = dc_model.predict_match_lambdas(test_arrays)
        matches_test_b = pd.DataFrame(
            {
                "match_id": test_arrays.match_id,
                "lambda_home": lambda_home_b,
                "lambda_away": lambda_away_b,
                "y_home": test_arrays.y_home.astype(int),
                "y_away": test_arrays.y_away.astype(int),
            }
        )
        print(f"  équipes du test set non vues à l'entraînement : {dc_model.n_unseen_teams_at_predict}")

        metrics_b, predictions_b = _evaluate(
            matches_test_b, lambda h, a: dixon_coles_matrix(h, a, dc_model.rho, tau_correction)
        )
        print(f"Modèle B -- log-loss test : {metrics_b['log_loss_exact_score']:.4f}")
        print(f"Modèle B -- Brier 1N2 test : {metrics_b['brier_score_1x2']:.4f}")
        print("Modèle B -- biais scores bas (prédit vs observé) :")
        print(pd.DataFrame(metrics_b["low_score_bias"]))

        # --- Comparaison ------------------------------------------------------
        delta_log_loss = metrics_a["log_loss_exact_score"] - metrics_b["log_loss_exact_score"]
        delta_brier = metrics_a["brier_score_1x2"] - metrics_b["brier_score_1x2"]
        print("\n=== Comparaison A vs B ===")
        print(f"Gain de log-loss (A - B, positif = B meilleur) : {delta_log_loss:+.4f}")
        print(f"Gain de Brier (A - B, positif = B meilleur)    : {delta_brier:+.4f}")

        results = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cutoff_date": CUTOFF_DATE.isoformat(),
            "n_train_rows": len(split.X_train),
            "n_test_rows": len(split.X_test),
            "n_matches_dropped_missing_features": dataset.n_matches_dropped_missing_features,
            "n_rows_dropped_missing_values": dataset.n_rows_dropped_missing_values,
            "model_a": {
                "feature_names": poisson_model.feature_names,
                "coefficients": poisson_model.result.params.to_dict(),
                "pvalues": poisson_model.result.pvalues.to_dict(),
                "metrics_test": metrics_a,
            },
            "model_b": {
                "xi_grid_search": xi_search_log,
                "xi_selected": best_xi,
                "gamma": dc_model.gamma,
                "rho": dc_model.rho,
                "delta": dict(zip(dc_model.delta_feature_names, dc_model.delta.tolist())),
                "n_teams": len(dc_model.team_ids),
                "reference_team_id": dc_model.reference_team_id,
                "n_unseen_teams_at_predict": dc_model.n_unseen_teams_at_predict,
                "metrics_test": metrics_b,
            },
            "comparison": {
                "delta_log_loss_a_minus_b": delta_log_loss,
                "delta_brier_a_minus_b": delta_brier,
            },
        }

        RESULTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\nRésultats bruts écrits dans {RESULTS_JSON_PATH}")


if __name__ == "__main__":
    main()
