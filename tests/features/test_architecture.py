"""Test d'architecture du scellé technique : une seule porte de lecture des matchs.

Dans `features/`, seul `sources.py` peut importer le modèle `Match` ou écrire du SQL sur
`staging.match`. Les notebooks n'importent du projet que `foot_predictor.features.sources`.
Les anciens modules (`features/legacy/`, remplacés, retrait en partie 4) sont hors de cette règle.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FEATURES = REPO / "src" / "foot_predictor" / "features"
NOTEBOOKS = REPO / "notebooks"

GATE = FEATURES / "sources.py"
STAGING_MATCH = re.compile(r"staging\.match\b")


def _feature_modules() -> list[Path]:
    modules = []
    for path in sorted(FEATURES.rglob("*.py")):
        if path == GATE or "legacy" in path.relative_to(FEATURES).parts:
            continue
        modules.append(path)
    return modules


def _imports_match_model(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "foot_predictor.db.models":
            if any(alias.name in {"Match", "*"} for alias in node.names):
                return True
        if isinstance(node, ast.Import) and any(alias.name == "foot_predictor.db.models" for alias in node.names):
            return True
    return False


def test_only_the_gate_reads_matches():
    offenders = []
    for path in _feature_modules():
        source = path.read_text(encoding="utf-8")
        if _imports_match_model(ast.parse(source)) or STAGING_MATCH.search(source):
            offenders.append(path.relative_to(REPO).as_posix())
    assert offenders == []


def test_the_gate_really_filters_in_sql():
    """Garde-fou sur la porte elle-même : le filtre du scellé est dans la requête."""
    source = GATE.read_text(encoding="utf-8")
    assert "where m.match_date < :upper" in source
    assert "check_seal(" in source


def _notebook_code(path: Path) -> str:
    cells = json.loads(path.read_text(encoding="utf-8")).get("cells", [])
    return "\n".join("".join(cell.get("source", [])) for cell in cells if cell.get("cell_type") == "code")


def test_notebooks_only_use_the_gate():
    offenders = []
    for path in sorted(NOTEBOOKS.rglob("*.ipynb")) if NOTEBOOKS.exists() else []:
        code = _notebook_code(path)
        modules = set(re.findall(r"(?:from|import)\s+(foot_predictor[\w.]*)", code))
        forbidden = {m for m in modules if m != "foot_predictor.features.sources"}
        if forbidden or re.search(r"\b(sqlalchemy|psycopg)\b", code) or "staging." in code:
            offenders.append(path.relative_to(REPO).as_posix())
    assert offenders == []
