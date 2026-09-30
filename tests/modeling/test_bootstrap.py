"""Bootstrap par blocs et Diebold-Mariano : cas à intervalle connu, déterminisme, blocs."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.modeling import bootstrap


def test_blocks_of_one_match_give_the_classical_interval():
    """Blocs d'un seul match, écarts i.i.d. : l'intervalle ≈ moyenne ± 1,96 σ / √n."""
    rng = np.random.default_rng(0)
    diff = rng.normal(0.01, 0.2, 4000)
    interval = bootstrap.block_bootstrap(diff, np.arange(4000), n_resamples=4000, seed=1)
    half = 1.96 * diff.std(ddof=1) / np.sqrt(len(diff))
    assert interval.low == pytest.approx(diff.mean() - half, abs=0.15 * half)
    assert interval.high == pytest.approx(diff.mean() + half, abs=0.15 * half)


def test_correlated_blocks_widen_the_interval():
    """Même écart répété dans chaque bloc de 10 : l'information est celle de 400 blocs, pas de 4000 matchs."""
    rng = np.random.default_rng(2)
    per_block = rng.normal(0.0, 0.2, 400)
    diff = np.repeat(per_block, 10)
    blocks = np.repeat(np.arange(400), 10)
    wide = bootstrap.block_bootstrap(diff, blocks, n_resamples=4000, seed=3)
    naive = bootstrap.block_bootstrap(diff, np.arange(4000), n_resamples=4000, seed=3)
    assert (wide.high - wide.low) > 2.5 * (naive.high - naive.low)  # √10 ≈ 3,2


def test_same_seed_same_interval_and_different_seed_differs():
    rng = np.random.default_rng(4)
    diff, blocks = rng.normal(size=500), np.repeat(np.arange(50), 10)
    first = bootstrap.block_bootstrap(diff, blocks, n_resamples=2000, seed=7)
    assert first == bootstrap.block_bootstrap(diff, blocks, n_resamples=2000, seed=7)
    assert first != bootstrap.block_bootstrap(diff, blocks, n_resamples=2000, seed=8)


def test_stratified_by_fold_keeps_each_fold():
    diff = np.concatenate([np.full(100, 1.0), np.full(100, 3.0)])
    blocks = np.arange(200)
    strata = np.repeat([2021, 2022], 100)
    interval = bootstrap.block_bootstrap(diff, blocks, strata, n_resamples=500, seed=0)
    assert interval.low == pytest.approx(2.0) and interval.high == pytest.approx(2.0)  # chaque pli garde sa taille


def test_empty_difference_is_refused():
    with pytest.raises(ValueError):
        bootstrap.block_bootstrap([0.1, np.nan], [1, 2])


def test_diebold_mariano_detects_a_clear_difference_and_not_noise():
    rng = np.random.default_rng(5)
    blocks = np.repeat(np.arange(300), 10)
    clear = bootstrap.diebold_mariano(rng.normal(0.05, 0.2, 3000), blocks)
    noise = bootstrap.diebold_mariano(rng.normal(0.0, 0.2, 3000), blocks)
    assert clear["p_value"] < 0.001
    assert noise["p_value"] > 0.01


def test_block_keys_use_round_then_iso_week():
    frame = pd.DataFrame(
        {
            "api_league_id": [39, 39, 61],
            "season_year": [2021, 2021, 2021],
            "round": ["Regular Season - 3", "Regular Season - 3", None],
            "match_day": [dt.date(2021, 8, 28), dt.date(2021, 8, 29), dt.date(2021, 8, 29)],
        }
    )
    keys = bootstrap.block_keys(frame).tolist()
    assert keys[0] == keys[1] == "39:2021:Regular Season - 3"
    assert keys[2] == "61:2021-W34"
