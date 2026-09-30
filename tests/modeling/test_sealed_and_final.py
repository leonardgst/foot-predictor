"""Test scellé (exécution, garde-fous) et entraînement final, sur données synthétiques. Sans base, sans Git réel."""

from __future__ import annotations

import datetime as dt
import json
import subprocess

import pytest

from foot_predictor.modeling import experiment, sealed
from foot_predictor.modeling.final import FinalTrainingError, train_final
from tests.modeling.synthetic import realistic_rows

SEALED_SPEC = """
name: scelle-essai
sealed_test: true
train_seasons: [2015, 2024]
population: top5
seed: 5
n_resamples: 200
models:
  - {id: M3, model: m3, params: {groups: [G0, G1]}}
  - {id: B1, model: b1, grid: {window: [1, 2]}}
comparisons:
  - [B1, M3]
"""


@pytest.fixture(scope="module")
def data():
    return realistic_rows(seasons=range(2015, 2027), teams_per_league=10, rounds=12)


@pytest.fixture
def spec(tmp_path):
    path = tmp_path / "scelle.yaml"
    path.write_text(SEALED_SPEC, encoding="utf-8")
    return path


def run(spec, data, tmp_path, **kwargs):
    return experiment.run_experiment(
        spec, reports_dir=tmp_path / "rapports", predictions_dir=tmp_path / "pred", data=data, manifest={},
        sealed_log=tmp_path / "journal.md", **kwargs,
    )  # fmt: skip


def test_sealed_file_requires_the_option_and_the_option_requires_a_sealed_file(spec, data, tmp_path):
    with pytest.raises(experiment.ExperimentError):
        run(spec, data, tmp_path)
    ordinary = tmp_path / "ordinaire.yaml"
    ordinary.write_text("name: x\nmodels:\n  - {id: M3, model: m3}\n", encoding="utf-8")
    with pytest.raises(experiment.ExperimentError):
        run(ordinary, data, tmp_path, sealed_test=True)


def test_sealed_evaluation_trains_on_development_and_tests_on_every_later_season(spec, data, tmp_path):
    report = run(spec, data, tmp_path, sealed_test=True)
    assert report["status"] == "ok", report.get("error")
    (fold,) = report["folds"]
    assert fold["season"] == 2025 and fold["name"].startswith("scellé")
    assert fold["eval_matches"] == data[(data["season_year"] >= 2025) & data["eval_population"]]["match_id"].nunique()
    inner = fold["models"]["B1"]["inner_validation"]
    assert len(inner) == 2  # fenêtre choisie sur 2024-25, jamais sur les saisons scellées
    log = (tmp_path / "journal.md").read_text(encoding="utf-8")
    assert experiment.SEALED_DONE in log and "B1 − M3" in log


def test_the_sealed_test_is_refused_a_second_time(spec, tmp_path):
    log = tmp_path / "journal.md"
    log.write_text(f"| 2026 | abc | {spec.as_posix()} | {experiment.SEALED_DONE}, rapport x |\n", encoding="utf-8")
    assert sealed.already_evaluated(spec.as_posix(), log)
    fake_git = lambda *args: subprocess.CompletedProcess(args, 0, stdout="", stderr="")  # noqa: E731
    with pytest.raises(sealed.SealedTestRefused):
        sealed.check_sealed_test_allowed(spec.as_posix(), log, git=fake_git)


def test_code_changed_since_the_tag_or_missing_tag_refuses_the_sealed_test():
    missing = lambda *args: subprocess.CompletedProcess(args, 1, stdout="", stderr="")  # noqa: E731
    with pytest.raises(sealed.SealedTestRefused, match="absent"):
        sealed.check_frozen(git=missing)

    def changed(*args):
        out = " src/foot_predictor/modeling/x.py | 2 +-" if args[0] == "diff" else ""
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    with pytest.raises(sealed.SealedTestRefused, match="modifiés"):
        sealed.check_frozen(git=changed)
    clean = lambda *args: subprocess.CompletedProcess(args, 0, stdout="", stderr="")  # noqa: E731
    sealed.check_frozen(git=clean)  # ne lève rien


def test_train_final_writes_a_model_and_its_card_and_never_overwrites(spec, data, tmp_path):
    dev = data[data["season_year"] <= 2024]
    kwargs = dict(data=dev, manifest={"version": "ds-test", "alembic_revision": "0007"}, models_root=tmp_path / "models",
                  cards_dir=tmp_path / "cartes", today=dt.date(2026, 10, 20))  # fmt: skip
    card = train_final(spec, "M3", **kwargs)
    folder = tmp_path / "models" / card["version"]
    assert (folder / "model.joblib").exists() and (folder / "model_card.json").exists()
    copy = json.loads((tmp_path / "cartes" / f"{card['version']}.json").read_text(encoding="utf-8"))
    assert copy["horizon"] == "H1" and copy["training"]["last_season"] == 2024
    assert copy["training"]["includes_sealed_matches"] is False and copy["alembic_revision"] == "0007"
    assert copy["model"]["features"] and copy["limits"]
    with pytest.raises(FinalTrainingError, match="écrasé"):
        train_final(spec, "M3", **kwargs)


def test_training_on_sealed_matches_requires_a_finished_sealed_test(spec, data, tmp_path):
    kwargs = dict(data=data, manifest={}, models_root=tmp_path / "models", cards_dir=tmp_path / "cartes",
                  sealed_log=tmp_path / "journal.md", today=dt.date(2026, 10, 21))  # fmt: skip
    with pytest.raises(FinalTrainingError, match="scellé"):
        train_final(spec, "M3", include_sealed=True, **kwargs)
    (tmp_path / "journal.md").write_text(f"| x | y | {spec.as_posix()} | {experiment.SEALED_DONE} |\n", "utf-8")
    card = train_final(spec, "M3", include_sealed=True, **kwargs)
    assert card["training"]["last_season"] == 2026 and card["training"]["includes_sealed_matches"] is True
