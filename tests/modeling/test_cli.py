"""Commande `python -m foot_predictor.modeling` : refus du test scellé, index."""

from __future__ import annotations

from foot_predictor.modeling import __main__ as cli
from foot_predictor.modeling import experiment


def test_sealed_test_option_is_refused_in_this_phase(tmp_path, capsys):
    assert cli.main(["evaluate", str(tmp_path / "x.yaml"), "--sealed-test"]) == 2
    assert "phase B" in capsys.readouterr().err


def test_index_command_writes_the_index(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(experiment.write_index, "__defaults__", (tmp_path,))
    assert cli.main(["index"]) == 0
    assert "**0 essai(s)**" in (tmp_path / "INDEX.md").read_text(encoding="utf-8")


def test_summary_writes_a_utf8_lf_file(tmp_path):
    import json

    report = {
        "id": "x", "seed": 1, "n_resamples": 10, "folds": [], "metrics": {}, "pooled": {}, "comparisons": [],
        "dataset": {"version": "ds-test"}, "git": {"commit": "abc"},
    }  # fmt: skip
    path = tmp_path / "x.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    output = tmp_path / "t.md"
    assert cli.main(["summary", str(path), "--output", str(output)]) == 0
    assert b"\r\n" not in output.read_bytes() and "rééchantillonnages" in output.read_text(encoding="utf-8")
