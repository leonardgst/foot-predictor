"""Registre des variables (`registry.yaml`) : lecture, validation, liste des colonnes.

Le registre est la liste de référence des colonnes du jeu de données. Une entrée peut
décrire plusieurs colonnes :

- `portee: [equipe, adversaire]` donne la colonne de l'équipe (`nom`) et celle de
  l'adversaire (`opp_<nom>`) ;
- un `nom` qui contient `{h}` donne une variable **distincte** par demi-vie de
  `parametres.demi_vie_jours`, qui porte son paramètre (`demi_vie_jours: 60`, par exemple).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parent / "registry.yaml"

REQUIRED_FIELDS = (
    "nom",
    "portee",
    "groupe",
    "definition",
    "source",
    "horizon",
    "disponible_en_live",
    "parametres",
    "historique_minimal",
    "manquant",
    "risque_fuite",
    "parade",
)
GROUPS = ("ID", "CIBLE", "G0", "G1", "G2", "G3", "G4", "G5", "G6")
FEATURE_GROUPS = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
HORIZONS = ("H1", "H2")
# Horizon de chaque groupe (ADR-0010, ADR-0047) : G0 à G3 avant composition ; G4 (entraîneur de la
# feuille de match), G5 (qualité du XI) et G6 (stabilité) avec la composition officielle.
GROUP_HORIZON = {"G0": "H1", "G1": "H1", "G2": "H1", "G3": "H1", "G4": "H2", "G5": "H2", "G6": "H2"}
HORIZON_RANK = {"H1": 1, "H2": 2}
OPPONENT_PREFIX = "opp_"


class RegistryError(ValueError):
    """Le registre est invalide."""


@dataclass(frozen=True)
class Variable:
    """Une colonne du jeu de données, avec sa fiche."""

    name: str
    group: str
    definition: str
    source: str
    horizon: str
    live: str
    parameters: dict = field(hash=False)
    minimal_history: str
    missing: str
    leak_risk: str
    leak_guard: str
    scope: str  # « equipe » ou « adversaire »
    entry: str  # nom de l'entrée du registre (avec « {h} » le cas échéant)


def load_entries(path: Path = PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = data.get("variables") or []
    validate_entries(entries)
    return entries


def validate_entries(entries: list[dict]) -> None:
    """Champs obligatoires, groupes et horizons connus, portée valide, pas de doublon."""
    seen = set()
    for entry in entries:
        missing = [f for f in REQUIRED_FIELDS if f not in entry or entry[f] in (None, "")]
        if missing and not (missing == ["parametres"] and entry.get("parametres") == {}):
            raise RegistryError(f"{entry.get('nom', '?')} : champs manquants {missing}")
        if entry["groupe"] not in GROUPS:
            raise RegistryError(f"{entry['nom']} : groupe inconnu {entry['groupe']}")
        if entry["groupe"] in FEATURE_GROUPS and entry["horizon"] not in HORIZONS:
            raise RegistryError(f"{entry['nom']} : une variable doit déclarer son horizon (H1 ou H2)")
        if entry["groupe"] in FEATURE_GROUPS and entry["horizon"] != GROUP_HORIZON[entry["groupe"]]:
            raise RegistryError(
                f"{entry['nom']} : le groupe {entry['groupe']} est de l'horizon "
                f"{GROUP_HORIZON[entry['groupe']]}, pas {entry['horizon']} (ADR-0010, ADR-0047)"
            )
        if not set(entry["portee"]) <= {"equipe", "adversaire"} or "equipe" not in entry["portee"]:
            raise RegistryError(f"{entry['nom']} : portée invalide {entry['portee']}")
        if "{h}" in entry["nom"] and not (entry.get("parametres") or {}).get("demi_vie_jours"):
            raise RegistryError(f"{entry['nom']} : « {{h}} » sans parametres.demi_vie_jours")
        if entry["nom"] in seen:
            raise RegistryError(f"{entry['nom']} : en double")
        seen.add(entry["nom"])


def variables(path: Path = PATH) -> list[Variable]:
    """Toutes les colonnes décrites par le registre, dans l'ordre du fichier."""
    out: list[Variable] = []
    for entry in load_entries(path):
        params = dict(entry.get("parametres") or {})
        half_lives = params.pop("demi_vie_jours", None) if "{h}" in entry["nom"] else None
        instances = [(entry["nom"], params)]
        if half_lives:
            instances = [(entry["nom"].replace("{h}", str(h)), params | {"demi_vie_jours": h}) for h in half_lives]
        for name, instance_params in instances:
            for scope in entry["portee"]:
                column = name if scope == "equipe" else OPPONENT_PREFIX + name
                out.append(
                    Variable(
                        name=column,
                        group=entry["groupe"],
                        definition=str(entry["definition"]).replace(
                            "{h}", str(instance_params.get("demi_vie_jours", "h"))
                        ),
                        source=str(entry["source"]),
                        horizon=str(entry["horizon"]),
                        live=str(entry["disponible_en_live"]),
                        parameters=instance_params,
                        minimal_history=str(entry["historique_minimal"]),
                        missing=str(entry["manquant"]).replace("{h}", str(instance_params.get("demi_vie_jours", "h"))),
                        leak_risk=str(entry["risque_fuite"]),
                        leak_guard=str(entry["parade"]).replace("{h}", str(instance_params.get("demi_vie_jours", "h"))),
                        scope=scope,
                        entry=entry["nom"],
                    )
                )
    names = [v.name for v in out]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise RegistryError(f"Colonnes en double après développement : {sorted(duplicates)}")
    return out


def columns(path: Path = PATH) -> list[str]:
    """Noms des colonnes du jeu de données, dans l'ordre du registre."""
    return [v.name for v in variables(path)]


def feature_columns(path: Path = PATH) -> list[str]:
    """Colonnes des groupes de variables (G0 à G6), sans identifiants ni cible."""
    return [v.name for v in variables(path) if v.group in FEATURE_GROUPS]


def check_model_horizon(model_columns, horizon: str, path: Path = PATH) -> None:
    """Refuse un modèle qui lit une variable d'un horizon plus tardif que le sien (ADR-0010).

    Un modèle H1 ne lit aucune variable H2 ; un modèle H2 lit les deux. Une colonne absente
    du registre est refusée aussi : on ne sait pas de quel horizon elle relève.
    """
    if horizon not in HORIZONS:
        raise RegistryError(f"Horizon inconnu : {horizon} (attendu : {', '.join(HORIZONS)})")
    known = {v.name: v for v in variables(path)}
    unknown = [c for c in model_columns if c not in known]
    if unknown:
        raise RegistryError(f"Colonnes absentes du registre, horizon inconnu : {unknown}")
    later = [
        c
        for c in model_columns
        if known[c].group in FEATURE_GROUPS and HORIZON_RANK[known[c].horizon] > HORIZON_RANK[horizon]
    ]
    if later:
        raise RegistryError(f"Modèle d'horizon {horizon} : variables d'un horizon plus tardif {later} (ADR-0010)")


def sha256(path: Path = PATH) -> str:
    """Empreinte du registre, gardée dans le manifeste du jeu de données."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
