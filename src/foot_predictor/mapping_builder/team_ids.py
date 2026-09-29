"""Brouillon du YAML « équipe football-data -> team.id API » (ADR-0008, règle 2).

Pour chaque division football-data et chaque saison où l'API a une liste de
matchs, les équipes sont appariées par le calendrier (`schedule_match`). Puis,
toutes saisons confondues :

- un nom apparié au **même** identifiant partout : retenu (`teams`) ;
- un nom apparié à deux identifiants différents : non apparié, listé ;
- un nom jamais apparié alors qu'il joue dans une saison couverte par l'API :
  non apparié, listé (`non_apparies`), avec la raison ;
- un nom présent seulement hors de la couverture API : `hors_api`. Le chargeur
  crée alors une équipe « hors_api », sans identifiant API (ADR-0008).

Le résultat est un **brouillon** : le fichier versionné est relu (diff Git)
avant d'être utilisé. Aucun nom de joueur n'y figure.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.football_data.download import FIRST_SEASON, LAST_SEASON
from foot_predictor.ingestion import raw_api
from foot_predictor.ingestion.football_data_csv import read_matches
from foot_predictor.ingestion.yaml_mappings import division_to_league
from foot_predictor.mapping_builder.schedule_match import Fixture, match_schedule


@dataclass
class TeamIdsDraft:
    teams: dict[str, int] = field(default_factory=dict)
    hors_api: list[str] = field(default_factory=list)
    non_apparies: dict[str, str] = field(default_factory=dict)
    # Décomptes pour le résumé : (division, saison) -> (appariées, non appariées)
    per_season: dict[tuple[str, int], tuple[int, int]] = field(default_factory=dict)


def build(raw_dir: Path, external_raw_dir: Path, seasons: range = range(FIRST_SEASON, LAST_SEASON + 1)) -> TeamIdsDraft:
    found: dict[str, Counter] = defaultdict(Counter)  # nom -> identifiants retenus (par saison)
    reasons: dict[str, list[str]] = defaultdict(list)
    covered_names: set[str] = set()
    all_names: set[str] = set()
    draft = TeamIdsDraft()

    for division, league in sorted(division_to_league().items()):
        for season in seasons:
            fd = read_matches(external_raw_dir, division, season)
            if not fd:
                continue
            names = {m.home for m in fd} | {m.away for m in fd}
            all_names |= names
            api = [
                Fixture(f.kickoff.date(), f.home_id, f.away_id)
                for f in raw_api.listed_fixtures(raw_dir, league, season)
                if f.kickoff is not None
            ]
            if not api:
                continue  # saison hors de la couverture API
            covered_names |= names
            result = match_schedule([Fixture(m.date, m.home, m.away) for m in fd], api)
            for name, api_id in result.mapping.items():
                found[name][api_id] += 1
            for name, reason in result.unmatched.items():
                reasons[name].append(f"{division} {season} : {reason}")
            draft.per_season[(division, season)] = (len(result.mapping), len(result.unmatched))

    for name in sorted(all_names):
        ids = found.get(name)
        if ids and len(ids) == 1:
            draft.teams[name] = next(iter(ids))
        elif ids:
            listed = ", ".join(f"{api_id} ({n} saison(s))" for api_id, n in sorted(ids.items()))
            draft.non_apparies[name] = f"identifiants différents selon les saisons : {listed}"
        elif name in covered_names:
            draft.non_apparies[name] = " ; ".join(reasons[name]) or "jamais apparié"
        else:
            draft.hors_api.append(name)
    return draft


HEADER = """\
# Équipes football-data -> team.id API-FOOTBALL (ADR-0008, règle 2 ; partie 2, sous-étape 2.5).
#
# BROUILLON PRODUIT PAR DU CODE, puis relu (diff Git) avant usage :
#   uv run python -m foot_predictor.mapping_builder teams \\
#       --raw-dir C:/foot-predictor/data/raw --external-raw-dir data/raw
# Méthode : appariement par le calendrier, sans comparer les noms
# (src/foot_predictor/mapping_builder/schedule_match.py). Une correspondance ambiguë
# n'est jamais devinée : elle reste dans `non_apparies`, avec sa raison.
#
# teams         nom football-data -> identifiant d'équipe API-FOOTBALL
# hors_api      noms présents seulement hors de la couverture API : le chargeur crée une
#               équipe « hors_api » (sans identifiant API)
# non_apparies  noms présents dans la couverture API, sans correspondance sûre : à relire
"""


def to_yaml(draft: TeamIdsDraft) -> str:
    """YAML trié, stable d'une exécution à l'autre (diff Git lisible)."""
    import yaml

    body = yaml.safe_dump(
        {"teams": draft.teams, "hors_api": sorted(draft.hors_api), "non_apparies": draft.non_apparies},
        allow_unicode=True,
        sort_keys=True,
        width=120,
    )
    return HEADER + "\n" + body
