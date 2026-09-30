"""Exécuteur d'expériences de bout en bout, sur données synthétiques : rapport, décision, index, échecs conservés."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from foot_predictor.modeling import experiment
from foot_predictor.modeling.models import MODELS
from tests.modeling.test_protocol import LeagueSide, Mean, synthetic_rows

SPEC = """
name: essai
folds: [2021, 2022]
seed: 11
n_resamples: 300
models:
  - {id: M, model: test_moyenne}
  - {id: L, model: test_championnat, grid: {window: [1, 3]}}
comparisons:
  - [M, L]
"""


@pytest.fixture(autouse=True)
def test_models(monkeypatch):
    monkeypatch.setitem(MODELS, "test_moyenne", Mean)
    monkeypatch.setitem(MODELS, "test_championnat", LeagueSide)


@pytest.fixture
def run(tmp_path):
    path = tmp_path / "essai.yaml"
    path.write_text(SPEC, encoding="utf-8")
    data = synthetic_rows(matches_per_season=60)

    def go(**kwargs):
        return experiment.run_experiment(
            path, reports_dir=tmp_path / "rapports", predictions_dir=tmp_path / "pred", data=data,
            manifest={"version": "ds-test"}, **kwargs,
        )  # fmt: skip

    return go, tmp_path


def test_report_contains_folds_metrics_comparisons_and_decision(run):
    go, tmp_path = run
    report = go(now=dt.datetime(2026, 9, 30, 12, tzinfo=dt.UTC))
    assert report["status"] == "ok", report.get("error")
    assert [f["season"] for f in report["folds"]] == [2021, 2022]
    fold = report["folds"][0]
    assert fold["models"]["L"]["params"]["window"] in (1, 3)
    assert len(fold["models"]["L"]["inner_validation"]) == 2  # deux candidats, validés sur 2020
    assert fold["intersection"] == fold["eval_matches"] == 60
    comparison = report["comparisons"][0]
    assert set(comparison["log_loss"]["per_fold"]) == {"2021", "2022"}
    assert set(comparison["decision"]) == {"i_gain_significant", "ii_positive_folds", "iii_calibration", "b_replaces_a"}
    assert report["pooled"]["L"]["matches"] == 120
    assert "slope" in report["pooled"]["L"]["calibration_over_2_5"]
    saved = json.loads((tmp_path / "rapports" / f"{report['id']}.json").read_text(encoding="utf-8"))
    assert saved["dataset"]["version"] == "ds-test"
    assert (tmp_path / "pred" / report["id"] / "predictions.parquet").exists()


def test_same_seed_gives_the_same_intervals(run):
    go, _ = run
    first = go(now=dt.datetime(2026, 9, 30, 12, tzinfo=dt.UTC))
    second = go(now=dt.datetime(2026, 9, 30, 13, tzinfo=dt.UTC))
    assert first["comparisons"] == second["comparisons"]


def test_failed_runs_are_kept_and_counted_in_the_index(run, tmp_path):
    go, _ = run
    go(now=dt.datetime(2026, 9, 30, 12, tzinfo=dt.UTC))
    bad = tmp_path / "echec.yaml"
    bad.write_text(
        "name: echec\nfolds: [2021]\nmodels:\n  - {id: L, model: test_championnat, params: {window: 0}}\n", "utf-8"
    )
    report = experiment.run_experiment(
        bad, reports_dir=tmp_path / "rapports", predictions_dir=tmp_path / "pred",
        data=synthetic_rows(), manifest={}, now=dt.datetime(2026, 9, 30, 14, tzinfo=dt.UTC),
    )  # fmt: skip
    assert report["status"] == "échec"
    index = (tmp_path / "rapports" / "INDEX.md").read_text(encoding="utf-8")
    assert "**2 essai(s)**, dont 1 en échec." in index


def test_invalid_spec_is_refused(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text("name: x\nmodels:\n  - {id: A, model: inconnu}\n", encoding="utf-8")
    with pytest.raises(experiment.ExperimentError):
        experiment.load_spec(path)


def test_sealed_fold_ends_as_a_failed_run(tmp_path):
    path = tmp_path / "scelle.yaml"
    path.write_text("name: scelle\nfolds: [2025]\nmodels:\n  - {id: M, model: test_moyenne}\n", encoding="utf-8")
    report = experiment.run_experiment(
        path, reports_dir=tmp_path, predictions_dir=tmp_path, data=synthetic_rows(), manifest={},
    )  # fmt: skip
    assert report["status"] == "échec" and "scellés" in report["error"]


def test_decision_rule_is_mechanical():
    item = {"log_loss": {"pooled": {"mean": 0.01, "excludes_zero": True}, "positive_folds": 3}}
    cal = lambda gap, slope: {"calibration_over_2_5": {"mean_abs_gap": gap, "slope": slope}}  # noqa: E731
    assert experiment.decision(item, cal(0.010, 1.0), cal(0.014, 1.05))["b_replaces_a"]
    assert not experiment.decision(item, cal(0.010, 1.0), cal(0.016, 1.0))["b_replaces_a"]  # +0,6 point
    assert not experiment.decision(item, cal(0.010, 1.0), cal(0.010, 1.12))["b_replaces_a"]  # pente
    two_folds = {"log_loss": {"pooled": {"mean": 0.01, "excludes_zero": True}, "positive_folds": 2}}
    assert not experiment.decision(two_folds, cal(0.01, 1), cal(0.01, 1))["b_replaces_a"]
    worse = {"log_loss": {"pooled": {"mean": -0.01, "excludes_zero": True}, "positive_folds": 0}}
    assert not experiment.decision(worse, cal(0.01, 1), cal(0.01, 1))["b_replaces_a"]
