"""Architecture de `modeling/` : aucune lecture directe de la base, tout passe par la porte (ADR-0028).

Hors `modeling/legacy/` (anciens modules, retrait en partie 5), aucun module de `modeling/`
n'importe les modèles SQLAlchemy ni n'écrit de SQL sur `staging` : les données viennent de
`features/sources.py` (`load_dataset`, `load_odds`), qui filtre le scellé en SQL.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODELING = REPO / "src" / "foot_predictor" / "modeling"
FORBIDDEN = re.compile(r"staging\.|foot_predictor\.db\b|from sqlalchemy|import sqlalchemy")


def test_modeling_reads_data_only_through_the_gate():
    offenders = []
    for path in sorted(MODELING.rglob("*.py")):
        if "legacy" in path.relative_to(MODELING).parts:
            continue
        if FORBIDDEN.search(path.read_text(encoding="utf-8")):
            offenders.append(path.relative_to(REPO).as_posix())
    assert offenders == []
