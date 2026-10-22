"""Relance unique du test scellé H1, après l'échec technique du premier lancement (ADR-0043, E-059).

    uv run python -m foot_predictor.sealed_rerun

Le premier lancement de `evaluate experiments/scelle_h1.yaml --sealed-test` (2026-10-22,
`scelle-h1-20261022T080319`) a tout calculé, puis il a planté à l'écriture du rapport. La clé
descriptive `test_from: 2025-07-01` est lue comme une date par YAML, et l'encodeur du rapport
(`modeling.experiment._json_default`) refuse les dates. Aucun résultat n'a été produit ni vu.

Ce lanceur refait le même calcul avec le code figé par `pre-scelle-h1`, sans le modifier. Il
appelle `experiment.run_experiment` et ne remplace, le temps de l'appel, que l'encodeur du
rapport : `run_experiment` cherche `_json_default` dans son module au moment d'écrire. Le
nouvel encodeur écrit en plus les dates au format ISO. Toute autre valeur qu'aucun des deux ne
sait écrire est mise sous forme de texte et signalée, plutôt que de faire perdre le calcul.

Il refuse de s'exécuter, sans rien lire ni écrire, si :

1. les garde-fous de `evaluate --sealed-test` refusent (tag, chemins figés, évaluation terminée) ;
2. l'arbre de travail a des modifications suivies : le rapport doit nommer un commit exact ;
3. le journal du scellé ne contient pas exactement les lignes du premier lancement : la relance
   n'a lieu qu'une fois, même si elle échoue à son tour ;
4. le fichier de prédictions du premier lancement manque ou a changé (sha256 relevé avant la
   décision, E-059).

Après le calcul, il compare le sha256 des nouvelles prédictions à celui du premier lancement :
deux empreintes égales montrent que la relance a refait exactement le même calcul.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from foot_predictor.modeling import experiment
from foot_predictor.modeling.sealed import SealedTestRefused, _git, check_sealed_test_allowed
from foot_predictor.seal import SEALED_TESTS_LOG

EXPERIMENT = "experiments/scelle_h1.yaml"
DATASET = "ds-2026-10-22-94969da0"
FIRST_RUN_ID = "scelle-h1-20261022T080319"
FIRST_PREDICTIONS = experiment.PREDICTIONS_DIR / FIRST_RUN_ID / "predictions.parquet"
FIRST_PREDICTIONS_SHA256 = "14b103d3292cef4b3055034b8aea88a368f0b37b99fd77e66c9c1f2cdd560e44"
FIRST_LAUNCH_LOG_LINES = 3
"""Lignes du journal laissées par le premier lancement : `build --sealed-test`, puis les deux lectures de l'évaluation."""

_FROZEN_DEFAULT = experiment._json_default


class RerunRefused(RuntimeError):
    """La relance n'est pas permise (ADR-0043) : rien n'a été lu ni écrit."""


@contextlib.contextmanager
def dates_in_report(fallbacks: list[str] | None = None) -> Iterator[list[str]]:
    """Le temps du bloc, l'encodeur du rapport écrit aussi les dates ; celui du code figé est remis ensuite.

    Les types écrits sous forme de texte, faute d'encodage prévu, sont ajoutés à la liste renvoyée.
    """
    fallbacks = [] if fallbacks is None else fallbacks

    def report_default(value):
        if isinstance(value, dt.date):  # dt.datetime et pd.Timestamp en héritent
            return value.isoformat()
        try:
            return _FROZEN_DEFAULT(value)
        except TypeError:
            fallbacks.append(type(value).__name__)
            return str(value)

    frozen = experiment._json_default
    experiment._json_default = report_default
    try:
        yield fallbacks
    finally:
        experiment._json_default = frozen


def usage_lines(log_path: Path) -> list[str]:
    """Lignes d'usage du journal du scellé (une par lecture ou par résultat)."""
    if not log_path.exists():
        return []
    return [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.startswith("| 20")]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_rerun_allowed(
    experiment_path: str = EXPERIMENT,
    *,
    log_path: Path = SEALED_TESTS_LOG,
    first_predictions: Path = FIRST_PREDICTIONS,
    first_sha256: str = FIRST_PREDICTIONS_SHA256,
    expected_log_lines: int = FIRST_LAUNCH_LOG_LINES,
    git: Callable = _git,
) -> None:
    """Lève `RerunRefused` si l'une des quatre conditions de l'ADR-0043 manque."""
    try:
        check_sealed_test_allowed(experiment_path, log_path, git=git)
    except SealedTestRefused as error:
        raise RerunRefused(str(error)) from error
    status = git("status", "--porcelain", "--untracked-files=no")
    if status.returncode != 0 or status.stdout.strip():
        raise RerunRefused(
            "Modifications suivies non committées (ou Git indisponible) : le rapport doit nommer un commit."
        )
    lines = usage_lines(log_path)
    if len(lines) != expected_log_lines or not all(experiment_path in line for line in lines):
        raise RerunRefused(
            f"Journal du scellé : {len(lines)} usage(s), {expected_log_lines} attendus (premier lancement seul). "
            "La relance n'a lieu qu'une fois (ADR-0043)."
        )
    if not first_predictions.exists():
        raise RerunRefused("Prédictions du premier lancement introuvables (E-059).")
    if sha256_file(first_predictions) != first_sha256:
        raise RerunRefused("Prédictions du premier lancement modifiées depuis le relevé de leur sha256 (E-059).")


def rerun(
    experiment_path: str = EXPERIMENT,
    dataset: str | None = DATASET,
    *,
    log_path: Path = SEALED_TESTS_LOG,
    reports_dir: Path = experiment.REPORTS_DIR,
    predictions_dir: Path = experiment.PREDICTIONS_DIR,
    first_predictions: Path = FIRST_PREDICTIONS,
    first_sha256: str = FIRST_PREDICTIONS_SHA256,
    expected_log_lines: int = FIRST_LAUNCH_LOG_LINES,
    git: Callable = _git,
    **run_kwargs,
) -> dict:
    """Vérifie les conditions, relance une fois le test scellé, compare les prédictions au premier lancement.

    `run_kwargs` (`data`, `manifest`, `odds`, `now`) passent à `run_experiment` : pour les tests seulement.
    """
    check_rerun_allowed(
        experiment_path, log_path=log_path, first_predictions=first_predictions, first_sha256=first_sha256,
        expected_log_lines=expected_log_lines, git=git,
    )  # fmt: skip
    with dates_in_report() as fallbacks:
        report = experiment.run_experiment(
            Path(experiment_path), reports_dir=reports_dir, predictions_dir=predictions_dir, sealed_test=True,
            dataset=dataset, sealed_log=log_path, **run_kwargs,
        )  # fmt: skip
    predictions = predictions_dir / report["id"] / "predictions.parquet"
    digest = sha256_file(predictions) if predictions.exists() else None
    return {
        "report": report,
        "predictions_sha256": digest,
        "same_predictions_as_first": digest == first_sha256,
        "written_as_text": sorted(set(fallbacks)),
    }


def main() -> int:
    try:
        result = rerun()
    except RerunRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    report = result["report"]
    print(f"Relance du test scellé (ADR-0043) : rapport {report['id']}, statut « {report['status']} ».")
    if result["written_as_text"]:
        print(f"Valeurs écrites sous forme de texte dans le rapport : {', '.join(result['written_as_text'])}.")
    if report["status"] != "ok":
        print(report.get("error", ""), file=sys.stderr)
        return 1
    same = "identique à" if result["same_predictions_as_first"] else "DIFFÉRENT de"
    print(f"Prédictions : sha256 {result['predictions_sha256']}, {same} celui du premier lancement.")
    print(f"Tableaux : uv run python -m foot_predictor.modeling summary reports/experiments/{report['id']}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
