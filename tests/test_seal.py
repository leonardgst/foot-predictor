"""Scellé technique (ADR-0012) : frontière, refus, journal des usages. Sans base."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from foot_predictor.seal import (
    H1_SEALED_EXPERIMENT,
    SEAL_DATE,
    SEALED_DONE,
    SealViolation,
    check_opened_for_inference,
    check_seal,
    count_sealed,
    sealed_test_finished,
)


def test_seal_date_is_first_of_july_2025():
    assert SEAL_DATE == dt.date(2025, 7, 1)


def test_dates_before_the_seal_are_accepted():
    dates = [dt.date(2024, 8, 17), pd.Timestamp("2025-06-30 23:59", tz="UTC")]
    assert check_seal(dates) == 0


def test_a_single_sealed_match_is_refused_without_option():
    dates = pd.Series(pd.to_datetime(["2025-06-30 20:00", "2025-07-01 00:00"], utc=True))
    with pytest.raises(SealViolation, match="1 match"):
        check_seal(dates)


def test_refusal_message_gives_only_a_count():
    """Le message ne doit rien dire du match scellé (ni date, ni équipe, ni score)."""
    with pytest.raises(SealViolation) as excinfo:
        check_seal([dt.date(2025, 8, 16), dt.date(2025, 8, 17)])
    message = str(excinfo.value)
    assert "2 match" in message
    assert "2025-08" not in message


def test_count_sealed_on_empty_input():
    assert count_sealed([]) == 0
    assert check_seal(pd.Series([], dtype="datetime64[ns, UTC]")) == 0


def test_sealed_test_requires_an_experiment_file(tmp_path):
    with pytest.raises(SealViolation, match="experiment"):
        check_seal([dt.date(2025, 8, 16)], sealed_test=True, log_path=tmp_path / "journal.md")
    assert not (tmp_path / "journal.md").exists()


def test_sealed_test_appends_one_line_to_the_log(tmp_path):
    log = tmp_path / "journal.md"
    n = check_seal(
        [dt.date(2024, 5, 1), dt.date(2025, 8, 16)],
        sealed_test=True,
        experiment="experiments/essai.yaml",
        log_path=log,
    )
    assert n == 1
    text = log.read_text(encoding="utf-8")
    assert text.startswith("# Journal des tests scellés")
    rows = [line for line in text.splitlines() if line.startswith("| 20")]
    assert len(rows) == 1
    assert "experiments/essai.yaml" in rows[0]
    assert "1 match(s) scellé(s) lus" in rows[0]

    check_seal([dt.date(2024, 5, 1)], sealed_test=True, experiment="experiments/essai.yaml", log_path=log)
    rows = [line for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("| 20")]
    assert len(rows) == 2  # chaque usage de l'option est journalisé, même sans match scellé


def test_the_versioned_log_only_lists_the_frozen_sealed_test():
    """Aucun usage pendant le développement ; depuis la phase B (4.16, après le gel du 2026-10-19),
    seulement le fichier figé par le tag `pre-scelle-h1`. La version intermédiaire (H2) ajoutera son fichier."""
    from foot_predictor.seal import SEALED_TESTS_LOG

    rows = [line for line in SEALED_TESTS_LOG.read_text(encoding="utf-8").splitlines() if line.startswith("| 20")]
    cells = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    assert all(date >= "2026-10-19" for date, *_ in cells)
    assert all(experiment == "experiments/scelle_h1.yaml" for _, _, experiment, _ in cells)


def test_finished_text_is_the_one_written_by_the_evaluation():
    """La porte ne doit pas importer `modeling/` : le texte est recopié, ce test garde les deux identiques."""
    from foot_predictor.modeling.experiment import SEALED_DONE as WRITTEN

    assert SEALED_DONE == WRITTEN and H1_SEALED_EXPERIMENT == "experiments/scelle_h1.yaml"


def test_opening_for_inference_waits_for_the_finished_h1_test(tmp_path):
    log = tmp_path / "journal.md"
    with pytest.raises(SealViolation, match="pas terminé"):  # journal absent
        check_opened_for_inference(log)
    log.write_text(
        f"| 2026-10-22 08:03 | abc | {H1_SEALED_EXPERIMENT} | accès autorisé, résultat à compléter |\n", "utf-8"
    )
    with pytest.raises(SealViolation, match="pas terminé"):  # lecture sans résultat : pas un test terminé
        check_opened_for_inference(log)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"| 2026-10-22 12:05 | def | experiments/autre.yaml | {SEALED_DONE}, rapport x |\n")
    with pytest.raises(SealViolation, match="pas terminé"):  # un autre fichier d'expérience ne compte pas
        check_opened_for_inference(log)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"| 2026-10-22 12:05 | def | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport y |\n")
    before = log.read_text(encoding="utf-8")
    check_opened_for_inference(log)  # ne lève rien
    assert sealed_test_finished(H1_SEALED_EXPERIMENT, log)
    assert log.read_text(encoding="utf-8") == before  # l'ouverture n'écrit rien au journal


def test_the_real_journal_opens_the_seal_for_inference():
    """Le test scellé H1 est terminé (4.16) : l'ouverture à l'inférence est acquise (ADR-0045)."""
    check_opened_for_inference()
