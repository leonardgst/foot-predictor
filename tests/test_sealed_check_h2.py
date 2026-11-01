"""Contrôle 1 du test scellé H2 (ADR-0050) : comparaison des colonnes H1, verdict seul. Sans base ni scellé."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from foot_predictor import sealed_check_h2 as chk


def h1_table() -> pa.Table:
    return pa.table(
        {
            "match_id": [3, 1, 2, 1],
            "team_id": [10, 10, 20, 20],
            "goals_for": pa.array([2, 0, 1, None], type=pa.int64()),
            "elo_pre": [1500.5, np.nan, 1490.25, 1510.0],
            "country": ["FR", "FR", "EN", None],
        }
    )


def h2_table(**changes) -> pa.Table:
    """Même contenu que H1, lignes dans un autre ordre, plus une colonne propre à H2."""
    base = h1_table().to_pydict()
    base.update(changes)
    table = pa.table(base)
    return table.take(pa.array([3, 2, 1, 0])).append_column("xi_quality", pa.array([0.1, 0.2, 0.3, 0.4]))


def test_identical_columns_are_identical_whatever_the_row_order_and_extra_columns() -> None:
    verdict = chk.compare_tables(h1_table(), h2_table())
    assert verdict.identical
    assert verdict.columns_compared == 5
    assert verdict.different_columns == ()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("elo_pre", [1500.5, np.nan, 1490.25, 1510.0000000000002]),  # un seul bit de mantisse
        ("goals_for", [2, 0, 1, 0]),  # un vide devenu valeur
        ("country", ["FR", "FR", "EN", "ES"]),
    ],
)
def test_one_changed_value_is_detected_and_only_its_column_is_named(column: str, value: list) -> None:
    verdict = chk.compare_tables(h1_table(), h2_table(**{column: value}))
    assert not verdict.identical
    assert verdict.different_columns == (column,)


def test_a_nan_is_not_a_missing_value() -> None:
    changed = h2_table(elo_pre=pa.array([1500.5, None, 1490.25, 1510.0], type=pa.float64()))
    verdict = chk.compare_tables(h1_table(), changed)
    assert verdict.different_columns == ("elo_pre",)


def test_negative_zero_differs_from_zero_at_the_bit_level() -> None:
    left = pa.table({"match_id": [1], "team_id": [1], "x": [0.0]})
    right = pa.table({"match_id": [1], "team_id": [1], "x": [-0.0]})
    assert chk.compare_tables(left, right).different_columns == ("x",)


def test_a_missing_h1_column_or_a_different_row_count_is_a_gap() -> None:
    assert not chk.compare_tables(h1_table(), h2_table().drop_columns(["country"])).identical
    assert chk.compare_tables(h1_table(), h2_table().slice(0, 3)).reasons == ("nombres de lignes différents",)


def test_the_verdict_text_never_contains_a_value(tmp_path, capsys) -> None:
    for name, table in {"h1": h1_table(), "h2": h2_table(goals_for=[2, 0, 1, 7])}.items():
        (tmp_path / name).mkdir()
        pq.write_table(table, tmp_path / name / "dataset.parquet")
    assert chk.main(["--h1", str(tmp_path / "h1"), "--h2", str(tmp_path / "h2")]) == 1
    out = capsys.readouterr().out
    assert "Colonnes différentes : goals_for." in out
    assert "1500" not in out and "VERDICT : ÉCART" in out


def test_dates_and_a_changed_type_are_compared_too() -> None:
    import datetime as dt

    base = {"match_id": [1, 2], "team_id": [1, 1], "match_date": [dt.date(2025, 7, 2), None]}
    same = chk.compare_tables(pa.table(base), pa.table(base))
    assert same.identical
    moved = chk.compare_tables(pa.table(base), pa.table({**base, "match_date": [dt.date(2025, 7, 3), None]}))
    assert moved.different_columns == ("match_date",)
    retyped = chk.compare_tables(pa.table(base), pa.table({**base, "match_date": ["2025-07-02", None]}))
    assert retyped.different_columns == ("match_date",)
