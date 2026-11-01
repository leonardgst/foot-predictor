"""Répétition du test scellé H2 avant le tag `pre-scelle-h2` (ADR-0050 ; préventions d'E-059 et d'E-060).

Le vrai `experiments/scelle_h2.yaml` (4 modèles, 10 000 rééchantillonnages, marché compris) passe de bout en bout
sur des données synthétiques avec les colonnes H2, par la même fonction que la commande, sans aucun lanceur de
secours. Sans base ni scellé.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from foot_predictor import sealed_rerun
from foot_predictor.modeling import experiment, sealed
from foot_predictor.modeling.summary import render
from foot_predictor.seal import REPO_ROOT
from tests.modeling.synthetic import realistic_rows, synthetic_odds, with_composition

H2_FILE = REPO_ROOT / "experiments" / "scelle_h2.yaml"
H1_FILE = REPO_ROOT / "experiments" / "scelle_h1.yaml"
NOW = dt.datetime(2026, 11, 2, 8, 0, tzinfo=dt.UTC)


def clean_git(*args):
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


@pytest.fixture(scope="module")
def data():
    """Saisons 2015-16 à 2026-27 ; G5 vide aux deux premières journées de chaque saison, comme au début réel."""
    frame = with_composition(realistic_rows(seasons=range(2015, 2027), teams_per_league=10, rounds=12))
    early = frame["round"].isin(["Regular Season - 1", "Regular Season - 2"])
    for column in ("xi_quality", "opp_xi_quality"):
        frame.loc[early, column] = np.nan
    return frame


def run(spec_path, data, tmp_path, now=NOW, **kwargs):
    return experiment.run_experiment(
        spec_path, reports_dir=tmp_path / "rapports", predictions_dir=tmp_path / "pred", data=data,
        manifest={"version": "ds-essai"}, odds=synthetic_odds(data), now=now, sealed_test=True,
        sealed_log=tmp_path / "journal.md", **kwargs,
    )  # fmt: skip


def copy_of(path, tmp_path, n_resamples: int | None = None):
    target = tmp_path / path.name
    shutil.copyfile(path, target)
    if n_resamples is not None:
        text = target.read_text(encoding="utf-8").replace("n_resamples: 10000", f"n_resamples: {n_resamples}")
        target.write_text(text, encoding="utf-8")
    return target


def test_the_list_is_the_one_of_adr_0050():
    """Référence : la procédure H1 du premier test ; modèle H2 : le M3_H2 retenu en 6.8 ; une comparaison décide."""
    spec = experiment.load_spec(H2_FILE)
    h1 = {m["id"]: m for m in experiment.load_spec(H1_FILE)["models"]}
    structures = {m["id"]: m for m in experiment.load_spec(REPO_ROOT / "experiments" / "structures_h2.yaml")["models"]}
    models = {m["id"]: m for m in spec["models"]}
    assert spec["sealed_test"] is True and spec["dataset"] is None
    assert (spec["train_seasons"], spec["seed"], spec["n_resamples"]) == ([2015, 2024], 20260930, 10000)
    assert models["M3_G0G2"] == h1["M3_G0G2"] and models["B1"] == h1["B1"]
    assert models["marche_avant_cloture"] == h1["marche_avant_cloture"]
    assert models["M3_H2"] == structures["M3_H2"]
    assert spec["comparisons"] == [["M3_G0G2", "M3_H2"], ["B1", "M3_H2"], ["M3_H2", "marche_avant_cloture"]]


def test_the_real_file_goes_through_the_frozen_report_encoder():
    """E-059 : aucune valeur que l'encodeur du rapport refuserait (la date est un texte)."""
    spec = experiment.load_spec(H2_FILE)
    assert json.loads(json.dumps(spec, default=experiment._json_default))["test_from"] == "2025-07-01"


def test_rehearsal_of_the_real_sealed_file_end_to_end(data, tmp_path):
    """Le vrai fichier, tel quel (10 000 rééchantillonnages), par `run_experiment` : rapport, tableaux, journal."""
    report = run(copy_of(H2_FILE, tmp_path), data, tmp_path)
    assert report["status"] == "ok", report.get("error")
    written = json.loads((tmp_path / "rapports" / f"{report['id']}.json").read_text(encoding="utf-8"))
    assert written["spec"]["test_from"] == "2025-07-01"
    (fold,) = written["folds"]
    assert fold["season"] == 2025 and fold["name"].startswith("scellé")
    assert fold["models"]["M3_H2"]["first_training_season"] == 2016  # rodage de G5 (D3)
    assert fold["models"]["M3_G0G2"]["first_training_season"] in (None, 2015)
    assert fold["excluded_by_intersection"] > 0  # G5 vide : écartés pour tous, jamais remplis
    for model in ("M3_G0G2", "M3_H2", "B1"):
        assert len(fold["models"][model]["inner_validation"]) >= 3  # choix sur 2024-25 seulement
    assert [(c["a"], c["b"]) for c in written["comparisons"]] == [tuple(c) for c in written["spec"]["comparisons"]]
    text = render(written)  # E-060 : relire les tableaux comme on lira ceux du vrai test
    assert "règle de décision | non applicable : 1 pli," in text and "remplace" not in text
    lines = sealed_rerun.usage_lines(tmp_path / "journal.md")
    assert len(lines) == 1  # données et cotes injectées : la seule ligne de résultat
    assert experiment.SEALED_DONE in lines[0] and "M3_G0G2 − M3_H2" in lines[0]


def test_two_runs_write_identical_predictions(data, tmp_path):
    """Le calcul ne dépend ni de l'heure ni de l'identifiant du lancement : contrôle par sha256 possible."""
    spec = copy_of(H2_FILE, tmp_path, n_resamples=200)
    digests = []
    for hour in (8, 9):
        report = run(spec, data, tmp_path, now=NOW.replace(hour=hour))
        assert report["status"] == "ok", report.get("error")
        digests.append(sealed_rerun.sha256_file(tmp_path / "pred" / report["id"] / "predictions.parquet"))
    assert digests[0] == digests[1]


def test_the_reference_predicts_like_the_first_sealed_test(data, tmp_path):
    """Contrôle prévu après le test (ADR-0050) : sur les mêmes données, `M3_G0G2` de scelle_h2 prédit comme celui de
    scelle_h1, au bit près, sur les matchs communs. Seule l'intersection (G5) diffère."""
    h2 = run(copy_of(H2_FILE, tmp_path, n_resamples=200), data, tmp_path)
    with sealed_rerun.dates_in_report():  # scelle_h1 garde sa date (E-059)
        h1 = run(copy_of(H1_FILE, tmp_path, n_resamples=200), data, tmp_path, now=NOW.replace(hour=9))
    assert h1["status"] == h2["status"] == "ok"

    def reference(report):
        frame = pd.read_parquet(tmp_path / "pred" / report["id"] / "predictions.parquet")
        return frame[frame["model"] == "M3_G0G2"].set_index("match_id")[["lambda_home", "lambda_away"]]

    first, second = reference(h1), reference(h2)
    assert len(second) < len(first)  # l'intersection de H2 écarte les matchs sans G5
    pd.testing.assert_frame_equal(first.loc[second.index], second, check_exact=True)


def test_the_guards_accept_the_h2_list_once(tmp_path):
    """Tag présent et chemins inchangés (Git simulé) : accepté ; refusé après une évaluation terminée de scelle_h2,
    pas après celle de scelle_h1."""
    log = tmp_path / "journal.md"
    path = "experiments/scelle_h2.yaml"
    log.write_text(
        f"| 2026-10-22 12:05 | abc | experiments/scelle_h1.yaml | {experiment.SEALED_DONE}, rapport x |\n", "utf-8"
    )
    sealed.check_sealed_test_allowed(path, log, git=clean_git)  # ne lève rien
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"| 2026-11-20 09:00 | def | {path} | {experiment.SEALED_DONE}, rapport y |\n")
    with pytest.raises(sealed.SealedTestRefused, match="déjà mené"):
        sealed.check_sealed_test_allowed(path, log, git=clean_git)
