"""Apport mesuré des groupes de variables de l'horizon H2, lu dans les rapports d'expériences (6.10).

Aucun chiffre n'est recopié : tout vient des rapports JSON générés par `modeling evaluate` (la
décision de 6.7 et les structures de 6.8), comme les tableaux de `docs/resultats/`. Le module ne
fait que choisir, dans le rapport, les comparaisons qui racontent le chemin de décision de
l'ADR-0048 et les mettre dans une forme que l'API sert et que l'interface affiche.

Une comparaison `A − B` du rapport est un écart de log-loss du total ; **positif**, B est meilleur
(le « gain » de B sur A). L'intervalle est à 95 %, par blocs (ADR-0037).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports" / "experiments"
ABLATION_REPORT = "ablations-h2-20261101T123436"
STRUCTURES_REPORT = "structures-h2-20261101T134102"

GROUPS = {
    "G6": ("Stabilité du onze", "titulaires communs avec le match précédent, cohésion, nouveaux titulaires"),
    "G5": ("Qualité du onze", "note moyenne des titulaires (rétrécie vers le poste), habituels absents, âge moyen"),
    "G4": ("Entraîneur", "ancienneté plafonnée à 365 jours, nouvel entraîneur (moins de 5 matchs)"),
}
DECISION_STEPS = (
    # (étape, groupe, modèle de départ, modèle ajouté, libellé de la base)
    (1, "G6", "A2_G0G2", "G6", "base H1 (G0 + G1 + G2)"),
    (2, "G5", "A2_G0G2", "G5", "base H1 (G6 n'étant pas retenu)"),
    (3, "G4", "G5", "G5_G4", "base H1 + G5"),
)
DIAGNOSTICS = (
    ("G5 à fenêtre d'apprentissage égale", "A2_depuis_2016", "G5", "contre la base H1 apprise dès 2016-17, comme G5"),
    ("G4 seul", "A2_G0G2", "G4", "contre la base H1"),
    ("G4 seul, à fenêtre égale", "A2_depuis_2017", "G4", "contre la base H1 apprise dès 2017-18, comme G4"),
    ("G6 + G5 + G4 ensemble", "A2_G0G2", "G6_G5_G4", "contre la base H1"),
)
STRUCTURES = (
    ("M6 (ridge) contre M3", "M3_H2", "M6_H2"),
    ("M7 (boosting) contre M3", "M3_H2", "M7_H2"),
)


class ContributionUnavailable(RuntimeError):
    """Rapport absent ou comparaison introuvable."""


def _read(name: str, reports_dir: Path) -> dict:
    path = reports_dir / f"{name}.json"
    if not path.exists():
        raise ContributionUnavailable(f"Rapport d'expérience absent : {name}.")
    return json.loads(path.read_text(encoding="utf-8"))


def _comparison(report: dict, a: str, b: str) -> dict:
    for item in report["comparisons"]:
        if item["a"] == a and item["b"] == b:
            return item
    raise ContributionUnavailable(f"Comparaison {a} − {b} absente du rapport {report.get('id')}.")


def _gain(item: dict) -> dict:
    pooled = item["log_loss"]["pooled"]
    return {
        "gain": pooled["mean"],
        "low": pooled["low"],
        "high": pooled["high"],
        "excludes_zero": bool(pooled["excludes_zero"]),
        "folds_won": int(item["log_loss"]["positive_folds"]),
        "folds": len(item["log_loss"]["per_fold"]),
        "matches": int(pooled["n"]),
    }


def load_contribution(reports_dir: Path = REPORTS_DIR) -> dict:
    """Chemin de décision de 6.7, diagnostics, structures de 6.8 et gain de G5 par tranche de journées."""
    ablations = _read(ABLATION_REPORT, reports_dir)
    structures = _read(STRUCTURES_REPORT, reports_dir)
    steps = []
    for number, group, start, added, base in DECISION_STEPS:
        item = _comparison(ablations, start, added)
        label, variables = GROUPS[group]
        steps.append(
            {
                "step": number,
                "group": group,
                "label": label,
                "variables": variables,
                "added_to": base,
                "retained": bool(item["decision"]["b_replaces_a"]),
                **_gain(item),
            }  # fmt: skip
        )
    diagnostics = [
        {"label": label, "against": against, **_gain(_comparison(ablations, start, added))}
        for label, start, added, against in DIAGNOSTICS
    ]
    g5 = _comparison(ablations, "A2_G0G2", "G5")
    by_round = [
        {"rounds": name, **{k: v for k, v in cell.items() if k in ("mean", "low", "high", "n", "excludes_zero")}}
        for name, cell in g5["by_round"].items()
    ]
    return {
        "model": "M3 (Poisson par équipe) sur G0 + G1 + G2 + G5",
        "unit": "écart de log-loss du total, en nats par match ; positif : le modèle avec le groupe est meilleur",
        "dataset": ablations["dataset"]["version"],
        "reports": {"decision": ablations["id"], "structures": structures["id"]},
        "folds": "4 plis de validation glissante, saisons 2021-22 à 2024-25",
        "steps": steps,
        "diagnostics": diagnostics,
        "structures": [
            {
                "label": label,
                **_gain(_comparison(structures, a, b)),
                "replaces": bool(_comparison(structures, a, b)["decision"]["b_replaces_a"]),
            }  # fmt: skip
            for label, a, b in STRUCTURES
        ],
        "g5_by_round": by_round,
        "notes": [
            "Le gain de G5 est minuscule (moins de 0,1 % du log-loss) et sa borne basse est à peine au-dessus de 0.",
            "À fenêtre d'apprentissage égale, l'intervalle contient 0 : une partie du gain tient à la fenêtre.",
            "Le test scellé H2 ne pourra presque sûrement pas distinguer un gain de cette taille de zéro (ADR-0047).",
        ],
    }
