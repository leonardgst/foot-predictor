"""Catalogue des variables, généré depuis le registre (`features catalogue`).

`docs/realisation/06_variables/catalogue.md` n'est jamais écrit à la main : un test échoue
s'il ne correspond plus au registre (`tests/features/test_catalogue.py`).
"""

from __future__ import annotations

from pathlib import Path

from foot_predictor.features import registry

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE_PATH = REPO_ROOT / "docs" / "realisation" / "06_variables" / "catalogue.md"

GROUP_TITLES = {
    "ID": "Identifiants et découpage",
    "CIBLE": "Cible (jamais une variable)",
    "G0": "G0 — Contexte",
    "G1": "G1 — Force globale (Elo)",
    "G2": "G2 — Attaque et défense (glissants)",
    "G3": "G3 — Calendrier (rejeu seulement)",
    "G4": "G4 — Entraîneur (horizon H2)",
    "G5": "G5 — Qualité du XI (horizon H2)",
    "G6": "G6 — Stabilité du onze (horizon H2)",
}


def _cell(value) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def _params(params: dict) -> str:
    if not params:
        return "—"
    return "; ".join(f"{k} = {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in params.items())


def render(path=registry.PATH) -> str:
    entries = registry.load_entries(path)
    variables = registry.variables(path)
    by_entry: dict[str, list[str]] = {}
    for variable in variables:
        by_entry.setdefault(variable.entry, []).append(variable.name)
    features = [v for v in variables if v.group in registry.FEATURE_GROUPS]
    groups = sorted({v.group for v in features})
    if {v.horizon for v in features} == {"H1"}:
        horizons = "toutes à l'horizon H1 (avant composition, ADR-0010)"
    else:
        horizons = "celles de G0 à G3 sont à l'horizon H1 (avant composition), celles de G4 à G6 à l'horizon H2 (avec composition, ADR-0010)"
    lines = [
        "# Catalogue des variables",
        "",
        "> **Fichier généré** par `python -m foot_predictor.features catalogue` depuis "
        "`src/foot_predictor/features/registry.yaml`. Ne pas le modifier à la main : modifier le registre, "
        "puis régénérer (un test vérifie qu'il est à jour).",
        "",
        f"{len(variables)} colonnes au jeu de données, dont {len(registry.feature_columns())} variables "
        f"({groups[0]} à {groups[-1]}), {horizons}. Une colonne `opp_…` est la même variable pour "
        "l'adversaire, lue sur sa ligne du même match. Règle temporelle : une variable du jour J n'utilise que des "
        "matchs terminés avant le jour J.",
        "",
    ]
    for group, title in GROUP_TITLES.items():
        group_entries = [e for e in entries if e["groupe"] == group]
        if not group_entries:
            continue
        lines += [f"## {title}", ""]
        for entry in group_entries:
            names = by_entry[entry["nom"]]
            lines += [
                f"### `{entry['nom']}`",
                "",
                f"- **Colonnes** : {', '.join(f'`{n}`' for n in names)}",
                f"- **Définition** : {_cell(entry['definition'])}",
                f"- **Source** : {_cell(entry['source'])}",
                f"- **Horizon** : {entry['horizon']} ; **disponible en live** : {_cell(entry['disponible_en_live'])}",
                f"- **Paramètres** : {_params(entry.get('parametres') or {})}",
                f"- **Historique minimal** : {_cell(entry['historique_minimal'])}",
                f"- **Valeur manquante** : {_cell(entry['manquant'])}",
                f"- **Risque de fuite** : {_cell(entry['risque_fuite'])} — {_cell(entry['parade'])}",
                "",
            ]
    return "\n".join(lines)


def write_catalogue(path: Path = CATALOGUE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")
    return path
