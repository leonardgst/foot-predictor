"""Apport des groupes H2 : lu dans les rapports d'expériences, jamais recopié (6.10)."""

from __future__ import annotations

import json

import pytest

from foot_predictor.inference import h2_contribution as C


def test_the_real_reports_give_the_decision_path_of_the_adr_0048():
    result = C.load_contribution()
    steps = {s["group"]: s for s in result["steps"]}
    assert [s["step"] for s in result["steps"]] == [1, 2, 3]
    assert not steps["G6"]["retained"] and steps["G5"]["retained"] and not steps["G4"]["retained"]
    g5 = steps["G5"]
    assert g5["gain"] == pytest.approx(0.00078, abs=5e-6) and g5["excludes_zero"] and g5["folds_won"] == 4
    assert g5["low"] == pytest.approx(0.00003, abs=5e-6) and g5["folds"] == 4 and g5["matches"] > 7000
    assert steps["G4"]["gain"] < 0  # G4 ajouté à G5 est moins bon
    assert result["dataset"] == "ds-2026-11-01-e0defb32"


def test_structures_and_diagnostics_are_the_published_ones():
    result = C.load_contribution()
    by_label = {s["label"]: s for s in result["structures"]}
    assert not by_label["M6 (ridge) contre M3"]["replaces"] and not by_label["M7 (boosting) contre M3"]["replaces"]
    assert by_label["M7 (boosting) contre M3"]["gain"] < 0 and by_label["M7 (boosting) contre M3"]["excludes_zero"]
    equal_window = next(d for d in result["diagnostics"] if d["label"].startswith("G5 à fenêtre"))
    assert not equal_window["excludes_zero"]  # à fenêtre égale, l'intervalle contient 0
    rounds = {r["rounds"]: r for r in result["g5_by_round"]}
    assert rounds["1-5"]["excludes_zero"] and rounds["1-5"]["mean"] > rounds["20-99"]["mean"] / 2
    assert result["notes"] and "écart de log-loss" in result["unit"]


def test_a_missing_report_is_reported_not_guessed(tmp_path):
    with pytest.raises(C.ContributionUnavailable, match="absent"):
        C.load_contribution(tmp_path)


def test_a_missing_comparison_is_reported(tmp_path):
    for name in (C.ABLATION_REPORT, C.STRUCTURES_REPORT):
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"id": name, "comparisons": [], "dataset": {"version": "x"}}), encoding="utf-8"
        )
    with pytest.raises(C.ContributionUnavailable, match="absente"):
        C.load_contribution(tmp_path)
