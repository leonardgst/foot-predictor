"""Contrôle 1 du test scellé H2 (ADR-0050) : les colonnes H1 du jeu H2 scellé sont celles du jeu H1 scellé.

    uv run python -m foot_predictor.sealed_check_h2 --h1 <dossier du jeu H1> --h2 <dossier du jeu H2>

Le jeu H2 scellé est construit avec `features build --horizon H2 --sealed-test`. Avant d'évaluer
quoi que ce soit, on vérifie que les colonnes qu'il a en commun avec le jeu H1 scellé
(`ds-2026-10-22-94969da0`) sont **identiques, ligne à ligne et au bit près**. Elles contiennent
des valeurs de matchs scellés (buts, tirs) : l'outil n'affiche donc **que le verdict**, des
décomptes et des noms de colonnes, jamais une valeur.

Ce fichier vit hors des chemins gelés par `pre-scelle-h2` (`modeling/`, `features/`, `seal.py`,
`experiments/`) : il ne lit que deux fichiers Parquet de `data/`, et aucun match par la porte.

Code de sortie : 0 si identiques, 1 sinon (arrêt avant l'évaluation, nouvelle ADR).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

KEY = ("match_id", "team_id")
"""Clé d'une ligne du jeu : un match vu du côté d'une équipe."""


@dataclass(frozen=True)
class Verdict:
    identical: bool
    rows_h1: int
    rows_h2: int
    columns_compared: int
    columns_only_h1: tuple[str, ...] = ()
    different_columns: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default=())


def _bits(column: pa.ChunkedArray) -> np.ndarray:
    """Flottants en bits exacts (un seul motif pour tous les NaN) ; le vide est distinct du NaN."""
    null = np.asarray(column.is_null().to_numpy(zero_copy_only=False))
    values = np.asarray(column.to_numpy(zero_copy_only=False), dtype=np.float64).copy()
    values[np.isnan(values)] = np.nan
    values[null] = 0.0
    return np.rec.fromarrays([null, values.view(np.uint64)], names="null,bits")


def _same(left: pa.ChunkedArray, right: pa.ChunkedArray) -> bool:
    """Même type et mêmes valeurs, vides compris ; flottants comparés bit à bit."""
    if left.type != right.type:
        return False
    if pa.types.is_floating(left.type):
        return bool(np.array_equal(_bits(left), _bits(right)))
    return left.combine_chunks().equals(right.combine_chunks())


def _sorted(table: pa.Table) -> pa.Table:
    return table.sort_by([(name, "ascending") for name in KEY])


def compare_tables(h1: pa.Table, h2: pa.Table) -> Verdict:
    """Compare les colonnes communes des deux tables, lignes alignées sur (match_id, team_id)."""
    shared = [name for name in h1.column_names if name in h2.column_names]
    only_h1 = tuple(name for name in h1.column_names if name not in h2.column_names)
    base = dict(rows_h1=h1.num_rows, rows_h2=h2.num_rows, columns_compared=len(shared), columns_only_h1=only_h1)
    reasons: list[str] = []
    if only_h1:
        reasons.append("des colonnes du jeu H1 manquent au jeu H2")
    if any(name not in shared for name in KEY):
        return Verdict(False, **base, reasons=(*reasons, "clé (match_id, team_id) absente"))
    if h1.num_rows != h2.num_rows:
        return Verdict(False, **base, reasons=(*reasons, "nombres de lignes différents"))
    left, right = _sorted(h1.select(shared)), _sorted(h2.select(shared))
    different = tuple(name for name in shared if not _same(left[name], right[name]))
    if different:
        reasons.append("valeurs différentes")
    return Verdict(not reasons, **base, different_columns=different, reasons=tuple(reasons))


def check(h1_dir: Path, h2_dir: Path) -> Verdict:
    return compare_tables(pq.read_table(h1_dir / "dataset.parquet"), pq.read_table(h2_dir / "dataset.parquet"))


def render(verdict: Verdict) -> str:
    lines = [
        f"Lignes : H1 {verdict.rows_h1}, H2 {verdict.rows_h2}.",
        f"Colonnes communes comparées : {verdict.columns_compared}.",
    ]
    if verdict.columns_only_h1:
        lines.append("Colonnes du jeu H1 absentes du jeu H2 : " + ", ".join(verdict.columns_only_h1) + ".")
    if verdict.different_columns:
        lines.append("Colonnes différentes : " + ", ".join(verdict.different_columns) + ".")
    lines.append(
        "VERDICT : identiques au bit près."
        if verdict.identical
        else "VERDICT : ÉCART (" + " ; ".join(verdict.reasons) + "). Arrêt avant l'évaluation, nouvelle ADR."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m foot_predictor.sealed_check_h2", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--h1", type=Path, required=True, help="dossier du jeu H1 scellé (ds-2026-10-22-94969da0)")
    parser.add_argument("--h2", type=Path, required=True, help="dossier du jeu H2 scellé")
    args = parser.parse_args(argv)
    verdict = check(args.h1, args.h2)
    print(render(verdict))
    return 0 if verdict.identical else 1


if __name__ == "__main__":
    sys.exit(main())
