"""Contrôle des CSV football-data stockés : lignes et colonnes par fichier, saisons vides.

Lecture seule. Ne lit que la structure (nombre de lignes de match et de
colonnes), jamais les scores : le décompte vaut aussi pour les saisons sous
scellé (ADR-0012).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.download import SUFFIX, season_dir


def decode(data: bytes) -> str:
    """UTF-8 (avec ou sans BOM) ; à défaut Windows-1252, l'encodage des plus anciens fichiers."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


@dataclass(frozen=True)
class FileShape:
    division: str
    season: int
    path: Path | None
    matches: int  # lignes dont la colonne « Div » est remplie
    columns: int  # colonnes nommées de l'en-tête

    @property
    def empty(self) -> bool:
        return self.matches == 0


def shape(data: bytes) -> tuple[int, int]:
    rows = list(csv.reader(io.StringIO(decode(data))))
    if not rows:
        return 0, 0
    header = rows[0]
    columns = sum(1 for name in header if name.strip())
    matches = sum(1 for row in rows[1:] if row and row[0].strip())
    return matches, columns


def check(raw_dir: Path, divisions: tuple[str, ...], seasons: range) -> list[FileShape]:
    """Forme de la dernière version de chaque fichier attendu (`path=None` s'il manque)."""
    shapes = []
    for season in seasons:
        for division in divisions:
            path = raw_bytes.latest(raw_dir, season_dir(season), division, SUFFIX)
            matches, columns = shape(path.read_bytes()) if path else (0, 0)
            shapes.append(FileShape(division, season, path, matches, columns))
    return shapes
