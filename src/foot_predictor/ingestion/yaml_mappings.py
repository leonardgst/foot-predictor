"""YAML de rapprochement versionnés (`ingestion/mappings/`) : lecture et validation.

Toute correction du référentiel passe par ces fichiers, rejoués par `load`
(ADR-0008, règle 4) ; aucune correction n'est faite en base.

| Fichier | Contenu |
|---|---|
| `competitions.yaml` | division football-data -> `league.id` API |
| `football_data_team_ids.yaml` | équipe football-data -> `team.id` API, `hors_api`, `non_apparies` |
| `player_aliases.yaml` | doublons : identifiant secondaire -> identifiant principal |
| `player_collisions.yaml` | exceptions à l'exclusion automatique des collisions (ADR-0020) |

Exception à la règle « aucun identifiant de joueur versionné » : les deux
fichiers de joueurs contiennent des identifiants API numériques, parce que
l'ADR-0008 exige des YAML versionnés. Jamais de nom ni de date de naissance.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

MAPPINGS_DIR = Path(__file__).parent / "mappings"


class MappingError(ValueError):
    """Un YAML de rapprochement ne respecte pas son schéma."""


def _load(name: str, directory: Path | None = None) -> dict:
    path = (directory or MAPPINGS_DIR) / name
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise MappingError(f"{name} : un dictionnaire est attendu à la racine")
    return data


def _int_map(data: object, where: str) -> dict:
    if data is None:
        return {}
    if not isinstance(data, dict) or not all(isinstance(v, int) and not isinstance(v, bool) for v in data.values()):
        raise MappingError(f"{where} : valeurs entières attendues")
    return data


def division_to_league(directory: Path | None = None) -> dict[str, int]:
    data = _int_map(_load("competitions.yaml", directory).get("football_data"), "competitions.yaml:football_data")
    if len(set(data.values())) != len(data):
        raise MappingError("competitions.yaml : deux divisions visent la même compétition API")
    return dict(data)


def football_data_teams(directory: Path | None = None) -> tuple[dict[str, int], set[str], dict[str, str]]:
    """(nom -> team.id API, noms hors API, noms non appariés et raison)."""
    data = _load("football_data_team_ids.yaml", directory)
    teams = _int_map(data.get("teams"), "football_data_team_ids.yaml:teams")
    hors_api = set(data.get("hors_api") or [])
    non_apparies = dict(data.get("non_apparies") or {})
    overlap = (set(teams) & hors_api) | (set(teams) & set(non_apparies)) | (hors_api & set(non_apparies))
    if overlap:
        raise MappingError(f"football_data_team_ids.yaml : noms dans deux sections : {sorted(overlap)}")
    return dict(teams), hors_api, non_apparies


def player_aliases(directory: Path | None = None) -> dict[int, int]:
    """Identifiant secondaire -> identifiant principal, sans cycle ni chaîne."""
    aliases = {
        int(k): v for k, v in _int_map(_load("player_aliases.yaml", directory).get("aliases"), "player_aliases").items()
    }
    for secondary, primary in aliases.items():
        if secondary == primary:
            raise MappingError(f"player_aliases.yaml : {secondary} renvoie vers lui-même")
        if primary in aliases:
            # Une chaîne a -> b -> c (ou un cycle) rendrait le résultat dépendant de l'ordre.
            raise MappingError(f"player_aliases.yaml : {primary} est à la fois principal et secondaire")
    return aliases


COLLISION_ACTIONS = ("keep", "exclude")


def player_collision_exceptions(directory: Path | None = None) -> dict[tuple[int, int], str]:
    """(identifiant de match API, identifiant de joueur API) -> « keep » ou « exclude ».

    Chaque exception doit citer sa preuve dans le brut (numéro, équipe, date de
    naissance) : ADR-0020, « ce que l'on s'interdit ».
    """
    exceptions: dict[tuple[int, int], str] = {}
    for index, item in enumerate(_load("player_collisions.yaml", directory).get("exceptions") or []):
        where = f"player_collisions.yaml:exceptions[{index}]"
        if not isinstance(item, dict) or set(item) != {"fixture", "player", "action", "preuve"}:
            raise MappingError(f"{where} : clés attendues fixture, player, action, preuve")
        if item["action"] not in COLLISION_ACTIONS or not str(item["preuve"]).strip():
            raise MappingError(f"{where} : action keep|exclude et preuve non vide attendues")
        key = (int(item["fixture"]), int(item["player"]))
        if key in exceptions:
            raise MappingError(f"{where} : exception en double")
        exceptions[key] = item["action"]
    return exceptions


@cache
def load_all() -> dict:
    """Tous les YAML du dépôt, validés (mis en cache : ils ne changent pas pendant un `load`)."""
    return {
        "division_to_league": division_to_league(),
        "football_data_teams": football_data_teams(),
        "player_aliases": player_aliases(),
        "player_collision_exceptions": player_collision_exceptions(),
    }
