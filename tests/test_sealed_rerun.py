"""Relance unique du test scellé H1 (ADR-0043, E-059) : encodeur, conditions, répétition. Sans base ni scellé."""

from __future__ import annotations

import datetime as dt
import json
import subprocess

import numpy as np
import pandas as pd
import pytest

from foot_predictor import sealed_rerun
from foot_predictor.modeling import experiment
from foot_predictor.modeling.models import market
from foot_predictor.modeling.summary import render
from foot_predictor.seal import REPO_ROOT
from tests.modeling.synthetic import realistic_rows

REAL_SPEC = (REPO_ROOT / sealed_rerun.EXPERIMENT).read_text(encoding="utf-8")


def fake_git(command: str = "", stdout: str = ""):
    """Git simulé : `stdout` pour la sous-commande `command`, sortie vide et succès pour les autres."""

    def git(*args):
        return subprocess.CompletedProcess(args, 0, stdout=stdout if args[0] == command else "", stderr="")

    return git


CLEAN_GIT = fake_git()


def first_launch_log(log, spec_path: str, lines: int = sealed_rerun.FIRST_LAUNCH_LOG_LINES) -> None:
    rows = [f"| 2026-10-22 08:0{i} | abc | {spec_path} | accès autorisé, résultat à compléter |" for i in range(lines)]
    log.write_text("# Journal\n\n" + "\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture
def first_launch(tmp_path):
    """Fichier d'expérience (le vrai), journal du premier lancement, prédictions du premier lancement."""
    spec = tmp_path / "scelle_h1.yaml"
    spec.write_text(REAL_SPEC, encoding="utf-8")
    log = tmp_path / "journal.md"
    first_launch_log(log, spec.as_posix())
    predictions = tmp_path / "premier" / "predictions.parquet"
    predictions.parent.mkdir()
    predictions.write_bytes(b"premier lancement")
    return {
        "experiment_path": spec.as_posix(), "log_path": log, "first_predictions": predictions,
        "first_sha256": sealed_rerun.sha256_file(predictions), "git": CLEAN_GIT,
    }  # fmt: skip


def check(first_launch, **changes):
    kwargs = first_launch | changes
    path = kwargs.pop("experiment_path")
    sealed_rerun.check_rerun_allowed(path, **kwargs)


def test_the_frozen_encoder_refuses_the_date_of_the_real_sealed_file():
    """E-059 : la clé `test_from` est une date ; l'encodeur figé la refuse, celui de la relance l'écrit."""
    spec = experiment.load_spec(REPO_ROOT / sealed_rerun.EXPERIMENT)
    assert isinstance(spec["test_from"], dt.date)
    with pytest.raises(TypeError):
        json.dumps(spec, default=experiment._json_default)
    with sealed_rerun.dates_in_report() as fallbacks:
        text = json.dumps(spec, default=experiment._json_default)
    assert json.loads(text)["test_from"] == "2025-07-01" and fallbacks == []


def test_the_frozen_encoder_is_put_back_even_after_an_error():
    with pytest.raises(ValueError), sealed_rerun.dates_in_report():
        assert experiment._json_default is not sealed_rerun._FROZEN_DEFAULT
        raise ValueError
    assert experiment._json_default is sealed_rerun._FROZEN_DEFAULT


def test_values_still_unknown_are_written_as_text_and_reported():
    with sealed_rerun.dates_in_report() as fallbacks:
        text = json.dumps({"n": np.int64(3), "chemin": REPO_ROOT}, default=experiment._json_default)
    assert json.loads(text)["n"] == 3 and fallbacks == [type(REPO_ROOT).__name__]


def test_the_rerun_is_allowed_with_the_first_launch_only(first_launch):
    check(first_launch)  # ne lève rien


@pytest.mark.parametrize("lines", [0, 2, 4, 6])
def test_the_rerun_happens_once_only(first_launch, lines):
    first_launch_log(first_launch["log_path"], first_launch["experiment_path"], lines)
    with pytest.raises(sealed_rerun.RerunRefused, match="une fois"):
        check(first_launch)


def test_a_line_of_another_experiment_refuses_the_rerun(first_launch):
    first_launch_log(first_launch["log_path"], "experiments/autre.yaml")
    with pytest.raises(sealed_rerun.RerunRefused, match="une fois"):
        check(first_launch)


def test_a_finished_sealed_test_refuses_the_rerun(first_launch):
    with first_launch["log_path"].open("a", encoding="utf-8") as handle:
        handle.write(f"| 2026-10-22 09:00 | abc | {first_launch['experiment_path']} | {experiment.SEALED_DONE} |\n")
    with pytest.raises(sealed_rerun.RerunRefused, match="déjà mené"):
        check(first_launch)


def test_changed_or_missing_first_predictions_refuse_the_rerun(first_launch, tmp_path):
    with pytest.raises(sealed_rerun.RerunRefused, match="modifiées"):
        check(first_launch, first_sha256="0" * 64)
    with pytest.raises(sealed_rerun.RerunRefused, match="introuvables"):
        check(first_launch, first_predictions=tmp_path / "absent.parquet")


def test_uncommitted_changes_or_changed_frozen_code_refuse_the_rerun(first_launch):
    with pytest.raises(sealed_rerun.RerunRefused, match="non committées"):
        check(first_launch, git=fake_git("status", " M x.py"))
    with pytest.raises(sealed_rerun.RerunRefused, match="modifiés"):
        check(first_launch, git=fake_git("diff", " x | 1 +"))


def synthetic_odds(data: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    ids = np.sort(data["match_id"].unique())
    frames = []
    for version in ("avant_cloture", "cloture"):
        over = rng.uniform(1.6, 2.4, len(ids))
        frames.append(
            pd.DataFrame({"match_id": ids, "version": version, "odds_over_2_5": over, "odds_under_2_5": 3.9 - over})
        )
    return market.market_probabilities(pd.concat(frames, ignore_index=True))


def test_without_the_new_encoder_the_real_sealed_file_fails_like_the_first_launch(tmp_path):
    """Reproduction d'E-059 : le calcul va au bout, les prédictions sont écrites, puis le rapport plante."""
    spec = tmp_path / "scelle_h1.yaml"
    spec.write_text(REAL_SPEC.replace("n_resamples: 10000", "n_resamples: 200"), encoding="utf-8")
    data = realistic_rows(seasons=range(2015, 2027), teams_per_league=10, rounds=12)
    now = dt.datetime(2026, 10, 22, 8, 3, 19, tzinfo=dt.UTC)
    with pytest.raises(TypeError, match="datetime.date"):
        experiment.run_experiment(
            spec, reports_dir=tmp_path / "rapports", predictions_dir=tmp_path / "pred", data=data, manifest={},
            odds=synthetic_odds(data), now=now, sealed_test=True, sealed_log=tmp_path / "journal.md",
        )  # fmt: skip
    assert (tmp_path / "pred" / "scelle-h1-20261022T080319" / "predictions.parquet").exists()
    assert list((tmp_path / "rapports").glob("*.json")) == []  # aucun rapport ; données injectées : aucun journal
    assert not (tmp_path / "journal.md").exists()


def test_rehearsal_of_the_real_sealed_file_end_to_end(first_launch, tmp_path):
    """Répétition de la relance avec le vrai `scelle_h1.yaml` (5 modèles, 10 000 rééchantillonnages)."""
    data = realistic_rows(seasons=range(2015, 2027), teams_per_league=10, rounds=12)
    kwargs = first_launch | {"reports_dir": tmp_path / "rapports", "predictions_dir": tmp_path / "pred"}
    path = kwargs.pop("experiment_path")
    result = sealed_rerun.rerun(
        path, None, data=data, manifest={"version": "ds-essai"}, odds=synthetic_odds(data), **kwargs
    )
    report = result["report"]
    assert report["status"] == "ok", report.get("error")
    assert result["written_as_text"] == [] and result["predictions_sha256"] and not result["same_predictions_as_first"]
    written = json.loads((tmp_path / "rapports" / f"{report['id']}.json").read_text(encoding="utf-8"))
    assert written["spec"]["test_from"] == "2025-07-01"
    assert [(c["a"], c["b"]) for c in written["comparisons"]] == [tuple(c) for c in written["spec"]["comparisons"]]
    text = render(written)  # E-060 : relire les tableaux comme on lira ceux du vrai test
    assert "règle de décision | non applicable : 1 pli," in text and "remplace" not in text
    lines = sealed_rerun.usage_lines(first_launch["log_path"])
    assert len(lines) == sealed_rerun.FIRST_LAUNCH_LOG_LINES + 1  # données et cotes injectées : la ligne de résultat
    assert experiment.SEALED_DONE in lines[-1] and "B1 − M3_G0G2" in lines[-1]
    with pytest.raises(sealed_rerun.RerunRefused):  # une seule relance
        sealed_rerun.rerun(path, None, data=data, manifest={}, odds=synthetic_odds(data), **kwargs)


def test_two_runs_of_the_same_sealed_file_write_identical_predictions(tmp_path):
    """Fondement du contrôle par sha256 : le calcul ne dépend ni de l'heure ni de l'identifiant du lancement."""
    spec = tmp_path / "scelle.yaml"
    spec.write_text(REAL_SPEC.replace("n_resamples: 10000", "n_resamples: 200"), encoding="utf-8")
    data = realistic_rows(seasons=range(2015, 2027), teams_per_league=10, rounds=12)
    digests = []
    for hour in (8, 9):
        now = dt.datetime(2026, 10, 22, hour, tzinfo=dt.UTC)
        with sealed_rerun.dates_in_report():
            report = experiment.run_experiment(
                spec, reports_dir=tmp_path / "rapports", predictions_dir=tmp_path / "pred", data=data, manifest={},
                odds=synthetic_odds(data), now=now, sealed_test=True, sealed_log=tmp_path / "journal.md",
            )  # fmt: skip
        assert report["status"] == "ok", report.get("error")
        digests.append(sealed_rerun.sha256_file(tmp_path / "pred" / report["id"] / "predictions.parquet"))
    assert digests[0] == digests[1]
