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
