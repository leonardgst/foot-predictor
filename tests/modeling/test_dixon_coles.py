"""Tests de `modeling/dixon_coles.py` : la fonction de correction tau (valeurs
attendues sur les 4 cas non triviaux, 1 partout ailleurs), et un test de
récupération de paramètres -- on simule des matchs avec des alpha/beta/gamma/
rho connus à l'avance, on ajuste le modèle dessus, et on vérifie que le MLE
retrouve des valeurs proches des vraies. Pas de base de données nécessaire ici
(données entièrement synthétiques)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.modeling.dixon_coles import fit_dixon_coles, tau_correction
from foot_predictor.modeling.evaluation import dixon_coles_matrix


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (0, 0, "one_minus_lambda_mu_rho"),
        (1, 0, "one_plus_mu_rho"),
        (0, 1, "one_plus_lambda_rho"),
        (1, 1, "one_minus_rho"),
    ],
)
def test_tau_correction_matches_dixon_coles_1997_formula(a, b, expected):
    lam, mu, rho = 1.4, 0.9, 0.15
    expected_values = {
        "one_minus_lambda_mu_rho": 1.0 - lam * mu * rho,
        "one_plus_mu_rho": 1.0 + mu * rho,
        "one_plus_lambda_rho": 1.0 + lam * rho,
        "one_minus_rho": 1.0 - rho,
    }
    assert tau_correction(a, b, lam, mu, rho) == pytest.approx(expected_values[expected])


@pytest.mark.parametrize("a, b", [(2, 0), (0, 2), (2, 2), (3, 1), (1, 3), (5, 5)])
def test_tau_correction_is_one_outside_the_four_low_score_cases(a, b):
    assert tau_correction(a, b, lambda_home=1.4, lambda_away=0.9, rho=0.3) == 1.0


# ---------------------------------------------------------------------------
# Récupération de paramètres sur données synthétiques
# ---------------------------------------------------------------------------

TRUE_ALPHA = {1: 0.0, 2: 0.35, 3: -0.25, 4: 0.6}  # team 1 = référence (plus petit id)
TRUE_BETA = {1: 0.1, 2: -0.15, 3: 0.2, 4: -0.3}
TRUE_GAMMA = 0.3
TRUE_RHO = -0.15
N_ROUNDS = 60  # chaque paire ordonnée (home, away) jouée N_ROUNDS fois


def _simulate_match(rng: np.random.Generator, home: int, away: int) -> tuple[int, int]:
    lambda_home = np.exp(TRUE_ALPHA[home] - TRUE_BETA[away] + TRUE_GAMMA)
    lambda_away = np.exp(TRUE_ALPHA[away] - TRUE_BETA[home])
    matrix = dixon_coles_matrix(lambda_home, lambda_away, TRUE_RHO, tau_correction, max_goals=8)
    flat_probs = matrix.flatten()
    flat_probs = flat_probs / flat_probs.sum()
    choice = rng.choice(len(flat_probs), p=flat_probs)
    return divmod(choice, matrix.shape[1])


def _build_synthetic_dataset() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    rng = np.random.default_rng(42)
    teams = list(TRUE_ALPHA.keys())
    records = []
    match_id = 0
    base_date = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)

    for round_idx in range(N_ROUNDS):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                match_id += 1
                goals_home, goals_away = _simulate_match(rng, home, away)
                match_date = base_date + dt.timedelta(days=match_id)
                records.append(
                    {"match_id": match_id, "team_id": home, "opponent_team_id": away,
                     "match_date": match_date, "competition": "Synthetic", "is_home": True, "y": goals_home}
                )
                records.append(
                    {"match_id": match_id, "team_id": away, "opponent_team_id": home,
                     "match_date": match_date, "competition": "Synthetic", "is_home": False, "y": goals_away}
                )

    frame = pd.DataFrame.from_records(records)
    X = frame[["is_home"]].astype(float)
    y = frame["y"]
    meta = frame[["match_id", "team_id", "opponent_team_id", "match_date", "competition", "is_home"]]
    return X, y, meta


def test_mle_recovers_known_alpha_beta_gamma_rho_on_synthetic_data():
    X, y, meta = _build_synthetic_dataset()

    model = fit_dixon_coles(X, y, meta, xi=0.0)

    assert model.gamma == pytest.approx(TRUE_GAMMA, abs=0.15)
    assert model.rho == pytest.approx(TRUE_RHO, abs=0.15)

    for team_id, true_alpha in TRUE_ALPHA.items():
        assert model.alpha[team_id] == pytest.approx(true_alpha, abs=0.25)
    for team_id, true_beta in TRUE_BETA.items():
        assert model.beta[team_id] == pytest.approx(true_beta, abs=0.25)
