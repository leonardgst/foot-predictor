"""Jeu de données : contrôles anti-fuite (rapport I.8), registre, scellé, déterminisme. Sans base."""

from __future__ import annotations

import datetime as dt
import itertools
import json

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features import registry, xg_proxy
from foot_predictor.features.dataset import build_frame, counts_of, write_snapshot
from foot_predictor.features.elo import EloParams
from foot_predictor.seal import SealViolation

PARAMS = EloParams(k=20, home_advantage=50, season_regression=0.2, goal_multiplier=True, initial_gap=100)
COEF = xg_proxy.XgProxyCoefficients(on_target=0.3, off_target=0.02, n_team_matches=0, seasons="test")


def synthetic_matches(seed: int = 0) -> pd.DataFrame:
    """Deux saisons d'une échelle anglaise (4 équipes en PL, 4 en Championship), une coupe, une Ligue des champions."""
    rng = np.random.default_rng(seed)
    rows, mid = [], 0

    def add(day, league, season, home, away, kind="league", round_="Regular Season - 1", played=True):
        nonlocal mid
        mid += 1
        goals = rng.integers(0, 4, 2) if played else [None, None]
        rows.append(
            {
                "match_id": mid,
                "match_date": pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=15),
                "match_day": dt.date.fromisoformat(day),
                "competition_id": {39: 1, 40: 2, 45: 3, 2: 4}[league],
                "api_league_id": league,
                "competition_kind": kind,
                "season_year": season,
                "round": round_,
                "home_team_id": home,
                "away_team_id": away,
                "home_goals_90": goals[0],
                "away_goals_90": goals[1],
                "status": "played" if played else "scheduled",
                "excluded": False,
                "home_shots_fd": int(rng.integers(5, 20)),
                "away_shots_fd": int(rng.integers(5, 20)),
                "home_sot_fd": int(rng.integers(0, 5)),
                "away_sot_fd": int(rng.integers(0, 5)),
                "is_regular_season": kind == "league" and round_.startswith("Regular Season"),
            }
        )

    start = dt.date(2019, 8, 3)
    for season in (2019, 2020):
        base = start + dt.timedelta(days=365 * (season - 2019))
        for week, (league, teams) in itertools.product(range(6), ((39, [1, 2, 3, 4]), (40, [5, 6, 7, 8]))):
            day = (base + dt.timedelta(days=7 * week)).isoformat()
            a, b, c, d = teams if week % 2 == 0 else teams[::-1]
            add(day, league, season, a, b)
            add(day, league, season, c, d)
        add((base + dt.timedelta(days=17)).isoformat(), 45, season, 1, 6, kind="cup", round_="3rd Round")
        add((base + dt.timedelta(days=24)).isoformat(), 2, season, 2, 99, kind="cup", round_="Group A")
    add("2020-06-20", 39, 2019, 1, 2)  # huis clos (période sûre, Angleterre)
    add("2021-01-02", 39, 2020, 3, 4, played=False)  # à venir : aucune ligne, aucune mise à jour
    return pd.DataFrame(rows)


def build(matches: pd.DataFrame) -> pd.DataFrame:
    return build_frame(matches, PARAMS, COEF)


def test_dataset_columns_are_exactly_the_registry():
    frame = build(synthetic_matches())
    assert list(frame.columns) == registry.columns()


def test_one_row_per_match_and_team_only_regular_season_played():
    matches = synthetic_matches()
    frame = build(matches)
    league_played = matches[(matches["competition_kind"] == "league") & (matches["status"] == "played")]
    assert len(frame) == 2 * len(league_played)
    assert not frame.duplicated(["match_id", "team_id"]).any()
    home = frame[frame["is_home"]].set_index("match_id")
    away = frame[~frame["is_home"]].set_index("match_id")
    assert (home["goals_for"] == away.loc[home.index, "goals_against"]).all()
    assert (home["elo_pre"] == away.loc[home.index, "opp_elo_pre"]).all()


def test_control_1_changing_the_result_of_m_does_not_change_the_row_of_m():
    matches = synthetic_matches()
    target = matches[(matches["api_league_id"] == 39) & (matches["season_year"] == 2020)]["match_id"].iloc[2]
    before = build(matches)
    changed = matches.copy()
    idx = changed.index[changed["match_id"] == target][0]
    changed.loc[idx, ["home_goals_90", "away_goals_90", "home_sot_fd", "away_sot_fd"]] = [9, 0, 30, 0]
    after = build(changed)
    features = [c for c in registry.columns() if c not in ("goals_for", "goals_against")]
    pd.testing.assert_frame_equal(
        before.loc[before["match_id"] == target, features].reset_index(drop=True),
        after.loc[after["match_id"] == target, features].reset_index(drop=True),
    )
    later = before["match_day"] > changed.loc[idx, "match_day"]
    assert not before.loc[later].equals(after.loc[later])  # le résultat compte bien pour la suite


@pytest.mark.parametrize("cut", [dt.date(2019, 9, 1), dt.date(2020, 1, 1), dt.date(2020, 8, 20)])
def test_control_2_invariance_to_the_cut_date(cut):
    matches = synthetic_matches()
    full = build(matches)
    truncated = build(matches[matches["match_day"] < cut])
    pd.testing.assert_frame_equal(
        full[full["match_day"] < cut].reset_index(drop=True),
        truncated[truncated["match_day"] < cut].reset_index(drop=True),
        check_exact=True,
    )


def test_control_3_two_matches_on_the_same_day_do_not_influence_each_other():
    matches = synthetic_matches()
    day = matches["match_day"].iloc[4]
    same_day = matches[matches["match_day"] == day]["match_id"].tolist()
    assert len(same_day) >= 2
    before = build(matches)
    changed = matches.copy()
    changed.loc[changed["match_id"] == same_day[0], ["home_goals_90", "away_goals_90"]] = [7, 7]
    after = build(changed)
    for mid in same_day[1:]:
        pd.testing.assert_frame_equal(
            before[before["match_id"] == mid].drop(columns=["goals_for", "goals_against"]).reset_index(drop=True),
            after[after["match_id"] == mid].drop(columns=["goals_for", "goals_against"]).reset_index(drop=True),
        )


def test_control_4_the_seal_applies_to_build():
    matches = synthetic_matches()
    sealed = matches.iloc[[0]].copy()
    sealed["match_date"] = pd.Timestamp("2025-08-16 15:00", tz="UTC")
    with pytest.raises(SealViolation):
        build(pd.concat([matches, sealed], ignore_index=True))


def test_behind_closed_doors_and_phase():
    frame = build(synthetic_matches())
    closed = frame[frame["match_day"] == dt.date(2020, 6, 20)]
    assert (closed["behind_closed_doors"] == 1).all()
    assert set(frame["phase"]) == {"apprentissage"}
    assert frame["eval_population"].sum() == (frame["api_league_id"] == 39).sum()


def test_snapshot_is_deterministic(tmp_path):
    frame = build(synthetic_matches())
    base = {"counts": counts_of(frame), "parameters": {"essai": 1}}
    today = dt.date(2026, 9, 29)
    path_a, manifest_a = write_snapshot(frame, base, tmp_path / "a", today)
    path_b, manifest_b = write_snapshot(build(synthetic_matches()), base, tmp_path / "b", today)
    assert manifest_a["version"] == manifest_b["version"]
    assert (path_a / "dataset.parquet").read_bytes() == (path_b / "dataset.parquet").read_bytes()
    assert json.loads((path_a / "manifest.json").read_text(encoding="utf-8"))["version"] == manifest_a["version"]
    assert (
        manifest_a["version"].startswith("ds-2026-09-29-") and len(manifest_a["version"]) == len("ds-2026-09-29-") + 8
    )


def test_latest_dataset_is_the_most_recent_not_the_last_name(tmp_path):
    """Deux versions du même jour : la plus récente est celle écrite en dernier, pas la dernière par nom."""
    import os

    from foot_predictor.features.sources import list_datasets

    for name, mtime in (("ds-2026-09-29-ffffffff", 1000), ("ds-2026-09-29-00000000", 2000)):
        folder = tmp_path / name
        folder.mkdir()
        manifest = folder / "manifest.json"
        manifest.write_text(json.dumps({"date": "2026-09-29"}), encoding="utf-8")
        os.utime(manifest, (mtime, mtime))
    assert list_datasets(tmp_path)[-1] == "ds-2026-09-29-00000000"


def test_round_and_shots_source_are_carried_as_identifiers():
    """`round` sert aux blocs du bootstrap, `shots_source` au contrôle du changement de source (ADR-0035)."""
    frame = build(synthetic_matches())
    assert (frame["round"] == "Regular Season - 1").all()
    assert (frame["shots_source"] == "football_data").all()  # pas de colonnes API dans ce jeu synthétique
    groups = {v.name: v.group for v in registry.variables()}
    assert groups["shots_source"] == groups["round"] == "ID"  # jamais des variables du modèle
    assert "shots_source" not in registry.feature_columns()


def _with_a_sealed_match() -> pd.DataFrame:
    matches = synthetic_matches()
    sealed = matches[matches["api_league_id"] == 39].iloc[[0]].copy()
    sealed["match_id"] = matches["match_id"].max() + 1
    sealed["match_date"] = pd.Timestamp("2025-08-16 15:00", tz="UTC")
    sealed["match_day"] = dt.date(2025, 8, 16)
    sealed["season_year"] = 2025
    sealed["status"] = "played"
    sealed["home_goals_90"], sealed["away_goals_90"] = 2, 1
    return pd.concat([matches, sealed], ignore_index=True)


def test_sealed_matches_are_refused_without_the_sealed_test_option():
    with pytest.raises(SealViolation):
        build_frame(_with_a_sealed_match(), PARAMS, COEF)


def test_sealed_test_build_adds_the_sealed_rows_with_prior_history_only():
    matches = _with_a_sealed_match()
    frame = build_frame(matches, PARAMS, COEF, sealed_test=True)
    sealed = frame[frame["season_year"] == 2025]
    assert len(sealed) == 2 and set(sealed["phase"]) == {"scelle"}
    # Règle temporelle inchangée : changer le résultat du match scellé ne change pas sa ligne.
    changed = matches.copy()
    changed.loc[changed["season_year"] == 2025, ["home_goals_90", "away_goals_90"]] = [9, 9]
    again = build_frame(changed, PARAMS, COEF, sealed_test=True)
    features = [c for c in registry.feature_columns() if c in frame.columns]
    pd.testing.assert_frame_equal(
        sealed[features].reset_index(drop=True), again[again["season_year"] == 2025][features].reset_index(drop=True)
    )
    # Les lignes d'avant le scellé sont identiques à celles d'un build ordinaire.
    ordinary = build_frame(synthetic_matches(), PARAMS, COEF)
    pd.testing.assert_frame_equal(frame[frame["season_year"] < 2025].reset_index(drop=True), ordinary)


def test_sealed_dataset_is_read_only_with_the_option_and_the_read_is_logged(tmp_path):
    from foot_predictor.features.sources import load_dataset

    frame = build_frame(_with_a_sealed_match(), PARAMS, COEF, sealed_test=True)
    folder, manifest = write_snapshot(frame, {"counts": counts_of(frame)}, tmp_path, dt.date(2026, 10, 20))
    with pytest.raises(SealViolation):
        load_dataset(manifest["version"], tmp_path)
    log = tmp_path / "journal.md"
    read, _ = load_dataset(
        manifest["version"], tmp_path, sealed_test=True, experiment="experiments/x.yaml", sealed_log=log
    )
    assert (read["phase"] == "scelle").sum() == 2
    assert "experiments/x.yaml" in log.read_text(encoding="utf-8")
