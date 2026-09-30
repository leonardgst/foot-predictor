"""Protocole : plis, contrôles anti-fuite (rapport I.8), intersection, exclusions comptées. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.modeling import protocol
from foot_predictor.modeling.models.base import MatchPredictions, Model, match_frame
from foot_predictor.seal import SealViolation


def synthetic_rows(seed: int = 0, seasons=range(2015, 2025), matches_per_season: int = 40) -> pd.DataFrame:
    """Lignes (match, équipe) d'un top 5 (39) et d'une D2 (40), avec une variable `x` parfois vide."""
    rng = np.random.default_rng(seed)
    rows, mid = [], 0
    for season in seasons:
        for league in (39, 40):
            for j in range(matches_per_season):
                mid += 1
                day = dt.date(season, 8, 1) + dt.timedelta(days=7 * (j // 4))
                goals = rng.poisson([1.6 if league == 39 else 1.2, 1.1])
                x = rng.normal(size=2)
                for side, is_home in ((0, True), (1, False)):
                    rows.append(
                        {
                            "match_id": mid, "team_id": 2 * j + side, "opp_team_id": 2 * j + 1 - side,
                            "is_home": is_home, "season_year": season, "api_league_id": league,
                            "eval_population": league == 39, "goals_for": int(goals[side]),
                            "goals_against": int(goals[1 - side]), "match_day": day,
                            "match_date": pd.Timestamp(day, tz="UTC"), "round": f"Regular Season - {j // 4 + 1}",
                            "x": np.nan if (mid % 17 == 0) else float(x[side]),
                        }
                    )  # fmt: skip
    return pd.DataFrame(rows)


class Mean(Model):
    """Modèle de test : les deux équipes marquent selon Poisson(moyenne d'apprentissage)."""

    name = "moyenne"

    def fit(self, rows):
        self.mu_ = float(rows["goals_for"].mean())
        return self

    def predict(self, rows):
        matches = match_frame(rows)
        lam = np.full(len(matches), self.mu_)
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), lam, lam)


class LeagueSide(Model):
    """Modèle de test : moyenne par championnat et par côté sur les `window` dernières saisons."""

    name = "championnat"

    def __init__(self, window: int = 2) -> None:
        if window < 1:
            raise ValueError("fenêtre < 1")
        super().__init__(window=window)

    def fit(self, rows):
        recent = rows[rows["season_year"] > rows["season_year"].max() - self.params["window"]]
        self.means_ = recent.groupby(["api_league_id", "is_home"])["goals_for"].mean().to_dict()
        return self

    def predict(self, rows):
        matches = match_frame(rows)
        league = matches["home_api_league_id"].to_numpy()
        home = np.array([self.means_[(lg, True)] for lg in league])
        away = np.array([self.means_[(lg, False)] for lg in league])
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), home, away)


class Spy(Model):
    """Retient les saisons vues à l'ajustement ; prédit comme `Mean` ; exige la variable `x`."""

    name = "spy"
    features = ("x",)
    seen: list = []

    def __init__(self, shrink: float = 0.0) -> None:
        super().__init__(shrink=shrink)

    def fit(self, rows):
        Spy.seen.append(sorted(rows["season_year"].unique().tolist()))
        self.mu_ = rows["goals_for"].mean() * (1 - self.params["shrink"])
        self.x_mean_ = rows["x"].mean()  # « standardisation » ajustée dans le pli
        return self

    def predict(self, rows):
        assert "goals_for" not in rows.columns and "goals_against" not in rows.columns
        matches = match_frame(rows)
        lam = np.full(len(matches), self.mu_)
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), lam, lam)


def test_four_folds_with_growing_windows():
    folds = protocol.folds()
    assert [f.test_season for f in folds] == [2021, 2022, 2023, 2024]
    assert list(folds[0].train_seasons) == list(range(2015, 2021))
    assert list(folds[3].train_seasons) == list(range(2015, 2024))
    assert folds[1].inner_valid_season == 2021 and list(folds[1].inner_train_seasons) == list(range(2015, 2021))


def test_sealed_season_is_refused():
    with pytest.raises(protocol.ProtocolError):
        protocol.folds([2025])


def test_training_never_sees_the_test_season_even_for_hyperparameters():
    data = synthetic_rows()
    Spy.seen = []
    fold = protocol.Fold(2022)
    protocol.select_and_fit(Spy, [{"shrink": 0.0}, {"shrink": 0.1}], data, fold, "top5", Spy.features)
    assert Spy.seen[0] == list(range(2015, 2021))  # validation interne : 2021 sert de validation, jamais 2022
    assert all(max(seen) < 2022 for seen in Spy.seen)
    assert Spy.seen[-1] == list(range(2015, 2022))  # réajustement sur tout l'apprentissage


def test_guard_refuses_a_test_row_in_training():
    data = synthetic_rows()
    with pytest.raises(protocol.ProtocolError):
        protocol._guard(data[data["season_year"] <= 2021], protocol.Fold(2021))


def test_guard_refuses_a_sealed_match():
    data = synthetic_rows(seasons=[2016])
    data.loc[0, "match_date"] = pd.Timestamp("2025-08-01", tz="UTC")
    with pytest.raises(SealViolation):
        protocol._guard(data, protocol.Fold(2021))


def test_changing_the_result_of_a_test_match_does_not_change_its_prediction():
    data = synthetic_rows()
    fold = protocol.Fold(2023)
    fit = protocol.select_and_fit(LeagueSide, [{"window": 2}], data, fold, "top5")
    before, _ = protocol.predict_fold(fit, data, fold)
    changed = data.copy()
    test_ids = changed.loc[(changed["season_year"] == 2023) & changed["eval_population"], "match_id"]
    changed.loc[changed["match_id"].isin(test_ids), ["goals_for", "goals_against"]] = 9
    fit_changed = protocol.select_and_fit(LeagueSide, [{"window": 2}], changed, fold, "top5")
    after, _ = protocol.predict_fold(fit_changed, changed, fold)
    np.testing.assert_array_equal(before.total, after.total)


def test_missing_values_are_excluded_and_counted_never_filled():
    data = synthetic_rows()
    fold = protocol.Fold(2021)
    fit = protocol.select_and_fit(Spy, [{}], data, fold, "top5", Spy.features)
    train = data[data["season_year"].between(2015, 2020) & (data["api_league_id"] == 39)]
    assert fit.excluded_train_rows == int(train["x"].isna().sum()) > 0
    predicted, missing = protocol.predict_fold(fit, data, fold, Spy.features)
    test = data[(data["season_year"] == 2021) & (data["api_league_id"] == 39)]
    assert missing == test.loc[test["x"].isna(), "match_id"].nunique() > 0
    assert len(predicted) + missing == test["match_id"].nunique()


def test_population_top5_d2_adds_the_second_division_to_training_only():
    data = synthetic_rows()
    fold = protocol.Fold(2021)
    top5 = protocol.select_and_fit(Mean, [{}], data, fold, "top5").model.mu_
    both = protocol.select_and_fit(Mean, [{}], data, fold, "top5_d2").model.mu_
    assert top5 != both
    rows = protocol.test_rows(data, 2021)
    assert set(rows["api_league_id"]) == {39}


def test_intersection_keeps_only_matches_predicted_by_every_model():
    a = MatchPredictions.independent_poisson([1, 2, 3], [1.0] * 3, [1.0] * 3)
    b = MatchPredictions.independent_poisson([2, 3, 4], [1.0] * 3, [1.0] * 3)
    assert protocol.intersection({"a": a, "b": b}).tolist() == [2, 3]


def test_fitted_quantities_come_from_the_fold_training_rows_only():
    """Ce qui s'ajuste (ici la moyenne de `x`, comme une standardisation) ne voit que l'apprentissage du pli."""
    data = synthetic_rows()
    fold = protocol.Fold(2022)
    fit = protocol.select_and_fit(Spy, [{}], data, fold, "top5", Spy.features)
    train = data[data["season_year"].between(2015, 2021) & (data["api_league_id"] == 39)]
    assert fit.model.x_mean_ == pytest.approx(train["x"].mean())
    assert fit.model.x_mean_ != pytest.approx(data.loc[data["api_league_id"] == 39, "x"].mean())
