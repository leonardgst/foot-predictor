"""`features build` lit l'état Git avant la lecture journalisée des matchs (E-061). Sans base."""

from __future__ import annotations

import contextlib
import datetime as dt
from pathlib import Path

import pandas as pd

from foot_predictor.features import build, sources


def test_the_manifest_reads_the_git_state_before_the_journaled_sealed_read(monkeypatch, tmp_path):
    written = []

    def journaled_read(*args, **kwargs):  # comme la porte : la ligne du journal, puis les matchs
        written.append(kwargs.get("sealed_test"))
        return pd.DataFrame()

    captured = {}

    def snapshot(frame, manifest_base, root, today):
        captured.update(manifest_base)
        return Path(root), manifest_base | {"version": "ds-essai"}

    class Engine:  # seule `connect` est appelée (`record=False`)
        def connect(self):
            return contextlib.nullcontext(None)

    monkeypatch.setattr(sources, "load_matches", journaled_read)
    monkeypatch.setattr(build, "git_dirty", lambda: bool(written))  # le journal suivi par Git ferait « modifié »
    monkeypatch.setattr(build, "git_commit", lambda: "9724829")
    monkeypatch.setattr(build, "database_trace", lambda connection: {"alembic_revision": "0008", "load_run_id": 7})
    monkeypatch.setattr(build, "build_frame", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(build, "counts_of", lambda frame: {"rows": 0})
    monkeypatch.setattr(build, "write_snapshot", snapshot)
    build.run_build(
        output_root=tmp_path, record=False, engine=Engine(), today=dt.date(2026, 10, 22),
        sealed_test=True, experiment="experiments/scelle_h1.yaml",
    )  # fmt: skip
    assert written == [True]  # lecture scellée faite
    assert captured["git_commit"] == "9724829" and captured["git_dirty"] is False
