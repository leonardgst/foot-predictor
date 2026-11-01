"""Tableaux générés d'un rapport : verdict de la règle de décision selon le nombre de plis (E-060). Sans base."""

from __future__ import annotations

from foot_predictor.modeling.summary import render


def report(seasons: list[str], decision: dict) -> dict:
    """Rapport minimal : une comparaison B1 − M, avec sa ligne de décision telle qu'écrite dans le JSON."""
    per_fold = {s: {"mean": 0.02} for s in seasons}
    return {
        "id": "essai", "seed": 1, "n_resamples": 10, "dataset": {"version": "ds-essai"}, "git": {"commit": "abc"},
        "folds": [{"name": s, "eval_matches": 10, "intersection": 10, "excluded_by_intersection": 0, "models": {}}
                  for s in seasons],
        "metrics": {},
        "pooled": {"M": {"small_totals": {"0": {"predicted": 0.06, "observed": 0.06, "brier": 0.05,
                                                "mean_abs_gap": 0.01, "slope": 1.0}}}},
        "comparisons": [{
            "a": "B1", "b": "M",
            "log_loss": {"pooled": {"mean": 0.0189, "low": 0.0102, "high": 0.0282}, "per_fold": per_fold,
                         "positive_folds": len(seasons), "diebold_mariano": {"p_value": 0.0}},
            "decision": decision,
        }],
    }  # fmt: skip


def test_a_sealed_report_written_before_the_fix_gets_no_replacement_verdict():
    """Le rapport du test scellé H1 (2026-10-22) porte encore « b_replaces_a: false » : on ne l'affiche plus."""
    old = {"i_gain_significant": True, "ii_positive_folds": False, "iii_calibration": True, "b_replaces_a": False}
    text = render(report(["2025"], old))
    assert "non applicable : 1 pli," in text
    assert "remplace" not in text
    assert "calibration poolée sur le pli unique" in text and "4 plis" not in text


def test_a_four_fold_report_keeps_its_verdict_and_title():
    decision = {"applicable": True, "i_gain_significant": True, "ii_positive_folds": True, "iii_calibration": True,
                "b_replaces_a": True}  # fmt: skip
    text = render(report(["2021", "2022", "2023", "2024"], decision))
    assert "| (i) oui, (ii) oui, (iii) oui | **M remplace B1** |" in text
    assert "calibration poolée sur les 4 plis" in text and "non applicable" not in text


def test_the_round_bucket_gains_are_tabulated_when_the_report_has_them():
    base = report(["2021", "2022", "2023", "2024"], {"applicable": True, "i_gain_significant": True,
                  "ii_positive_folds": True, "iii_calibration": True, "b_replaces_a": True})  # fmt: skip
    base["comparisons"][0]["by_round"] = {
        "1-5": {"mean": 0.011, "low": -0.002, "high": 0.024, "n": 700},
        "20-99": {"mean": 0.004, "low": 0.001, "high": 0.007, "n": 3000},
    }
    text = render(base)
    assert "par tranche de journées" in text
    assert "| B1 | M | 1-5 | 700 | +0.01100 | [-0.00200 ; +0.02400] |" in text
    assert "20-99" in text
    assert "par tranche de journées" not in render(report(["2021"], {"applicable": False}))
