"""Estimation de la constante de rétrécissement de `xi_quality` : retrouve k sur des données simulées. Sans base."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features.xi_quality_estimation import estimate_shrinkage


def simulate(sigma2: float, tau2: float, players: int = 3000, seed: int = 20260930) -> pd.DataFrame:
    """Notes de w minutes = θ + bruit de variance σ²/w, avec θ de variance τ² (un seul poste)."""
    rng = np.random.default_rng(seed)
    theta = rng.normal(6.8, np.sqrt(tau2), players)
    rows = []
    for p in range(players):
        minutes = rng.integers(10, 91, rng.integers(3, 25))
        ratings = theta[p] + rng.normal(0.0, np.sqrt(sigma2 / minutes))
        rows.append(
            pd.DataFrame(
                {
                    "player": p,
                    "bucket": "Midfielder",
                    "weight": minutes.astype(float),
                    "weighted_rating": minutes * ratings,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


@pytest.mark.parametrize(("sigma2", "tau2"), [(30.0, 0.15), (12.0, 0.05)])
def test_recovers_the_shrinkage_constant(sigma2, tau2):
    result = estimate_shrinkage(simulate(sigma2, tau2))
    assert result["shrinkage_minutes"] == pytest.approx(sigma2 / tau2, rel=0.1)
    assert result["tau2"] == pytest.approx(tau2, rel=0.1)


def test_unusable_appearances_are_ignored():
    data = simulate(30.0, 0.15, players=500)
    noise = data.head(100).assign(weight=0.0, weighted_rating=0.0)
    assert (
        estimate_shrinkage(pd.concat([data, noise]))["shrinkage_minutes"]
        == estimate_shrinkage(data)["shrinkage_minutes"]
    )


def test_no_between_player_variance_is_refused():
    constant = pd.DataFrame({"player": range(50), "bucket": "Defender", "weight": 90.0, "weighted_rating": 90 * 6.5})
    with pytest.raises(ValueError, match="non positive"):
        estimate_shrinkage(constant.assign(player=lambda d: d["player"] // 2))
