"""Jeu H2 (G0 à G6) : colonnes H1 inchangées, jointure sur (match, équipe), anti-fuite, scellé. Sans base."""

from __future__ import annotations

import contextlib
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features import build, registry, sources
from foot_predictor.features.dataset import build_frame, build_frame_h2
from foot_predictor.seal import SealViolation
from tests.features.test_dataset import COEF, PARAMS, synthetic_matches

K = 500.0
H2_FEATURES = [c for c in registry.columns() if c not in registry.columns(horizon="H1")]


def synthetic_compositions(matches: pd.DataFrame, seed: int = 1) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compositions et feuilles de match des matchs de championnat joués : 11 titulaires par équipe, un peu de rotation."""
    rng = np.random.default_rng(seed)
    league = matches[(matches["competition_kind"] == "league") & (matches["status"] == "played")]
    lineups, sheets = [], []
    for _, row in league.iterrows():
        for team in (row["home_team_id"], row["away_team_id"]):
            pool = [team * 100 + i for i in range(14)]  # 14 joueurs par équipe, 11 débutent
            starters = rng.choice(pool, 11, replace=False)
            for player in starters:
                lineups.append(
                    {
                        "match_id": row["match_id"],
                        "team_id": team,
                        "api_player_id": int(player),
                        "started": True,
                        "position_bucket": ["Goalkeeper", "Defender", "Midfielder", "Attacker"][int(player) % 4],
                        "stats_position_bucket": None,
                        "rating": float(np.round(rng.uniform(5.5, 8.0), 1)),
                        "minutes": 90,
                        "birth_date": pd.Timestamp("1990-01-01") + pd.Timedelta(days=int(player) * 37),
                    }
                )
            sheets.append(
                {
                    "match_id": row["match_id"],
                    "team_id": team,
                    "api_coach_id": 7000 + int(team) + (int(row["season_year"]) - 2019) * 10,
                    "unknown_starters": 0,
                    "collision_excluded": 0,
                }
            )
    lineups = pd.DataFrame(lineups)
    lineups["rating"] = lineups["rating"].astype("Float64")
    lineups["minutes"] = lineups["minutes"].astype("Int64")
    return lineups, pd.DataFrame(sheets).astype({"api_coach_id": "Int64"})


def build_h2(matches, lineups, sheets):
    return build_frame_h2(matches, lineups, sheets, PARAMS, COEF, shrinkage_minutes=K)


@pytest.fixture(scope="module")
def inputs():
    matches = synthetic_matches()
    return (matches, *synthetic_compositions(matches))


@pytest.fixture(scope="module")
def frame(inputs):
    return build_h2(*inputs)


def test_columns_are_exactly_the_registry_with_the_h2_groups(frame):
    assert list(frame.columns) == registry.columns()
    assert len(H2_FEATURES) == 28  # 14 colonnes par équipe, et autant pour l'adversaire
    assert {registry.GROUP_HORIZON[v.group] for v in registry.variables() if v.name in H2_FEATURES} == {"H2"}


def test_h1_columns_are_identical_to_the_h1_dataset(inputs, frame):
    """Le jeu H2 ne change aucune valeur du jeu H1 : mêmes lignes, même ordre, mêmes colonnes, au bit près."""
    matches = inputs[0]
    h1 = build_frame(matches, PARAMS, COEF)
    pd.testing.assert_frame_equal(frame[registry.columns(horizon="H1")], h1, check_exact=True)


def test_opponent_columns_are_the_opponent_row_of_the_same_match(frame):
    own = [c for c in H2_FEATURES if not c.startswith("opp_")]
    home = frame[frame["is_home"]].set_index("match_id")
    away = frame[~frame["is_home"]].set_index("match_id")
    for column in own:
        pd.testing.assert_series_equal(
            home[f"opp_{column}"], away.loc[home.index, column].rename(f"opp_{column}"), check_names=False
        )
        pd.testing.assert_series_equal(
            away[f"opp_{column}"], home.loc[away.index, column].rename(f"opp_{column}"), check_names=False
        )


def test_first_matches_stay_empty_instead_of_being_filled(frame):
    first_day = frame["match_day"].min()
    first = frame[frame["match_day"] == first_day]
    assert first[["xi_overlap_prev", "xi_cohesion_ewm_h5", "xi_quality", "xi_regulars_missing"]].isna().all().all()
    assert first["coach_is_new"].eq(1).all() and first["coach_tenure_days"].eq(0).all()  # entraîneur qui arrive
    assert frame["xi_mean_age"].notna().all()  # ne dépend pas de l'historique


def test_h2_values_exist_later_in_the_season(frame):
    late = frame[frame["match_day"] >= dt.date(2020, 1, 1)]
    for column in ("xi_overlap_prev", "xi_cohesion_ewm_hinf", "xi_new_starters", "xi_quality", "coach_tenure_days"):
        assert late[column].notna().any(), column


@pytest.mark.parametrize("cut", [dt.date(2019, 9, 1), dt.date(2020, 1, 1), dt.date(2020, 8, 20)])
def test_invariance_to_the_cut_date_including_the_compositions(inputs, frame, cut):
    """Contrôle anti-fuite n° 2 à l'horizon H2 : matchs, compositions et feuilles tronqués à la même date."""
    matches, lineups, sheets = inputs
    kept = matches[matches["match_day"] < cut]
    truncated = build_h2(
        kept, lineups[lineups["match_id"].isin(kept["match_id"])], sheets[sheets["match_id"].isin(kept["match_id"])]
    )
    pd.testing.assert_frame_equal(
        frame[frame["match_day"] < cut].reset_index(drop=True),
        truncated[truncated["match_day"] < cut].reset_index(drop=True),
        check_exact=True,
    )


def test_changing_the_composition_of_m_does_not_change_the_h2_row_of_earlier_matches(inputs, frame):
    matches, lineups, sheets = inputs
    played = matches[(matches["competition_kind"] == "league") & (matches["status"] == "played")]
    last = played.sort_values(["match_day", "match_id"])["match_id"].iloc[-1]  # le dernier match par date
    changed = lineups.copy()
    changed.loc[changed["match_id"] == last, "rating"] = 3.0
    changed.loc[changed["match_id"] == last, "api_player_id"] += 5000
    again = build_h2(matches, changed, sheets)
    before = frame[frame["match_id"] != last].reset_index(drop=True)
    after = again[again["match_id"] != last].reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after, check_exact=True)


SIX_YEARS = pd.Timedelta(days=2192)  # 2019-08-03 → 2025-08-03 : toute la table passe sous scellés


def shifted_six_years(matches, lineups, sheets):
    """La même table, six ans plus tard (dates, saisons et naissances) : les variables doivent être les mêmes."""
    matches = matches.copy()
    matches["match_date"] += SIX_YEARS
    matches["match_day"] = (pd.to_datetime(matches["match_day"]) + SIX_YEARS).dt.date
    matches["season_year"] += 6
    lineups = lineups.assign(birth_date=lineups["birth_date"] + SIX_YEARS)
    return matches, lineups, sheets


def test_sealed_matches_get_their_h2_values_like_any_other(inputs, frame):
    """Jeu du test scellé H2 (ADR-0050) : refusé sans `sealed_test` ; avec, les lignes scellées ont leurs variables
    H2, calculées comme les autres (mêmes valeurs qu'avant le décalage de six ans), sans borne de saison cachée."""
    shifted = shifted_six_years(*inputs)
    with pytest.raises(SealViolation):
        build_frame_h2(*shifted, PARAMS, COEF, shrinkage_minutes=K)
    sealed = build_frame_h2(*shifted, PARAMS, COEF, shrinkage_minutes=K, sealed_test=True)
    assert set(sealed["season_year"]) == {2025, 2026} and set(sealed["phase"]) == {"scelle"}
    assert sealed[H2_FEATURES].notna().any().all()
    pd.testing.assert_frame_equal(sealed[H2_FEATURES], frame[H2_FEATURES], check_exact=True)


def test_run_build_reads_the_sealed_compositions_for_the_sealed_h2_dataset(monkeypatch, tmp_path):
    """`--horizon H2 --sealed-test` : matchs, compositions et feuilles de match lus par la porte avec le scellé levé
    et le fichier d'expérience (chaque lecture journalisée), puis `build_frame_h2` avec `sealed_test`."""
    reads, built = {}, {}

    def gate(name):
        def read(*args, **kwargs):
            reads[name] = (kwargs.get("sealed_test"), kwargs.get("experiment"))
            return pd.DataFrame({"api_league_id": [39], "competition_id": [1]})

        return read

    class Engine:  # seule `connect` est appelée (`record=False`)
        def connect(self):
            return contextlib.nullcontext(None)

    for name in ("load_matches", "load_lineups", "load_team_sheets"):
        monkeypatch.setattr(sources, name, gate(name))
    monkeypatch.setattr(build, "build_frame_h2", lambda *args, **kwargs: built.update(kwargs) or pd.DataFrame())
    monkeypatch.setattr(build, "database_trace", lambda connection: {"alembic_revision": "0008", "load_run_id": 7})
    monkeypatch.setattr(build, "counts_of", lambda frame: {"rows": 0})
    monkeypatch.setattr(build, "write_snapshot", lambda frame, base, root, today: (root, base | {"version": "ds-x"}))
    build.run_build(
        output_root=tmp_path, record=False, engine=Engine(), today=dt.date(2026, 11, 20), horizon="H2",
        sealed_test=True, experiment="experiments/scelle_h2.yaml",
    )  # fmt: skip
    assert reads == dict.fromkeys(reads, (True, "experiments/scelle_h2.yaml")) and len(reads) == 3
    assert built["sealed_test"] is True


def test_run_build_refuses_an_unknown_horizon():
    with pytest.raises(ValueError, match="Horizon inconnu"):
        build.run_build(horizon="H3", engine=object())


def test_h2_manifest_parameters_name_the_g4_to_g6_settings():
    parameters = build.frozen_parameters("H2")
    assert parameters["xi_quality"]["shrinkage_minutes"] > 0
    assert parameters["coach"] == {"tenure_cap_days": 365, "new_coach_matches": 5}
    assert "xi_quality" not in build.frozen_parameters("H1")
    assert build.scope("H2")["horizon"] == "H2"
