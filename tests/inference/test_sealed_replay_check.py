"""Garde du modèle testé (ADR-0052, §2) : choix des jours, fichier absent, empreintes inscrites dans l'ADR."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from foot_predictor.inference import check
from foot_predictor.seal import REPO_ROOT


def days(*values: dt.date, repeat: dict[dt.date, int] | None = None) -> pd.Series:
    repeat = repeat or {}
    expanded = [d for d in values for _ in range(repeat.get(d, 1))]
    return pd.Series(expanded, index=range(len(expanded)))


def test_the_sampled_days_cover_both_sealed_seasons_without_duplicates():
    start = dt.date(2025, 8, 15)
    series = days(
        *(start + dt.timedelta(days=7 * k) for k in range(40)),  # 2025-26
        dt.date(2026, 8, 15),
        dt.date(2026, 9, 12),
        dt.date(2026, 10, 18),  # 2026-27
        repeat={dt.date(2026, 9, 12): 5, dt.date(2025, 12, 5): 4},
    )
    chosen = check.sealed_replay_days(series)
    labels = [reason for _, reason in chosen]
    assert chosen[0] == (dt.date(2025, 8, 15), "premier jour de 2025-26")
    assert "milieu de 2025-26" in labels and "jour le plus chargé de 2026-27" in labels
    assert (dt.date(2026, 9, 12), "jour le plus chargé de 2026-27") in chosen
    assert len({day for day, _ in chosen}) == len(chosen)  # un jour retenu une seule fois


def test_a_missing_prediction_file_makes_the_check_fail_without_reading_the_database(tmp_path):
    report = check.run_sealed_replay_check(horizon="H2", experiments_root=tmp_path)
    assert report["reference_found"] is False and report["all_reproduced"] is False
    report["date"] = "2026-11-01"
    assert "Fichier de prédictions absent" in check.render_sealed_replay(report)


def test_the_hashes_of_the_check_are_the_ones_written_in_the_adr():
    text = (REPO_ROOT / "docs" / "decisions" / "ADR-0052-ouverture-rejeu-scelle.md").read_text(encoding="utf-8")
    for report_id, _, sha in check.SEALED_REPLAY_REFERENCE.values():
        assert len(sha) == 64 and sha in text and report_id in text
