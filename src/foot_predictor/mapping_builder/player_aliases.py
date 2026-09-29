"""Brouillon du YAML des doublons de joueurs (ADR-0008, règle 3 : une personne, deux identifiants).

Les groupes candidats sont ceux de `raw_check` (même nom, même date de
naissance, identifiants différents), obtenus en réutilisant son contrôle sans
le modifier (règles du gel). Un groupe n'est retenu **automatiquement** que si
ses identifiants ne jouent jamais le même match, ni le même jour : sinon ce
sont peut-être deux personnes (homonymes nés le même jour), et le groupe reste
hors du YAML, compté comme « douteux ».

Identifiant principal : celui qui a le plus de présences ; à égalité, le plus
petit. Le YAML ne contient que des identifiants numériques, jamais de nom.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from foot_predictor.collect.api_football.plan import load_config
from foot_predictor.quality import raw_check

TIERS = ["P1", "P2", "P3"]


@dataclass
class AliasesDraft:
    groups: int = 0
    retained: int = 0
    doubtful: int = 0
    aliases: dict[int, int] = field(default_factory=dict)  # secondaire -> principal


def choose(groups: list[list[int]], fixtures: dict[int, set[int]], days: dict[int, set[int]]) -> AliasesDraft:
    """Décision pure, testable : `fixtures` et `days` donnent les matchs et les jours de chaque identifiant."""
    draft = AliasesDraft(groups=len(groups))
    for ids in groups:
        ids = sorted(set(ids))
        together = any(
            fixtures.get(a, set()) & fixtures.get(b, set()) or days.get(a, set()) & days.get(b, set())
            for i, a in enumerate(ids)
            for b in ids[i + 1 :]
        )
        if together:
            draft.doubtful += 1
            continue
        primary = min(ids, key=lambda pid: (-len(fixtures.get(pid, ())), pid))
        for pid in ids:
            if pid != primary:
                draft.aliases[pid] = primary
        draft.retained += 1
    return draft


def build(raw_dir: Path) -> AliasesDraft:
    checker = raw_check.RawChecker(raw_dir, load_config(raw_check.DEFAULT_CONFIG_PATH), TIERS)
    result = checker.run()
    groups = [ids for _, ids in result.duplicates]
    wanted = {pid for ids in groups for pid in ids}
    cols = {name: np.frombuffer(values, dtype=np.int64) for name, values in checker.appearances.columns.items()}
    mask = np.isin(cols["player"], list(wanted))
    fixtures: dict[int, set[int]] = defaultdict(set)
    days: dict[int, set[int]] = defaultdict(set)
    for pid, fid, day in zip(
        cols["player"][mask].tolist(), cols["fixture"][mask].tolist(), cols["day"][mask].tolist(), strict=True
    ):
        fixtures[pid].add(fid)
        days[pid].add(day)
    return choose(groups, fixtures, days)


HEADER = """\
# Doublons de joueurs : identifiant API secondaire -> identifiant API principal
# (ADR-0008, règle 3 ; partie 2, sous-étape 2.5).
#
# BROUILLON PRODUIT PAR DU CODE, puis relu (diff Git) avant usage :
#   uv run python -m foot_predictor.mapping_builder player-aliases --raw-dir C:/foot-predictor/data/raw
# Groupes candidats : même nom et même date de naissance dans les profils (raw_check).
# Retenus seulement si les identifiants ne jouent jamais le même match ni le même jour ;
# les groupes douteux restent hors de ce fichier (décompte dans le retour de la partie 2).
# Principal : l'identifiant qui a le plus de présences (à égalité, le plus petit).
# Exception assumée à la règle « aucun identifiant de joueur versionné » : l'ADR-0008
# exige un YAML versionné. Jamais de nom ni de date de naissance ici.
"""


def to_yaml(draft: AliasesDraft) -> str:
    import yaml

    body = yaml.safe_dump({"aliases": dict(sorted(draft.aliases.items()))}, sort_keys=False)
    return HEADER + "\n" + body
