"""
Rapprochement approximatif de noms d'équipe entre une source étrangère
(Understat, API-Football) et l'ensemble des noms canoniques (dérivés de
football-data + son mapping existant). Basé sur difflib (stdlib, pas de
dépendance supplémentaire) avec une normalisation adaptée au football
(accents, sigles FC/CF/AC, underscores Understat).

Deux niveaux de confiance :
- AUTO_ACCEPT_THRESHOLD : la correspondance est écrite directement dans le YAML.
- REVIEW_THRESHOLD : la meilleure correspondance est proposée mais marquée
  pour relecture manuelle (score insuffisant pour être auto-acceptée).
- En dessous : aucune correspondance proposée, marqué à compléter à la main.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

AUTO_ACCEPT_THRESHOLD = 0.84
REVIEW_THRESHOLD = 0.55

REVIEW_MARKER = "REVIEW_"  # préfixe pour repérer les lignes à vérifier dans le YAML brouillon

# Surnoms/abréviations fréquents qui n'ont AUCUN recouvrement de caractères
# avec le nom complet (le fuzzy matching seul ne peut pas les rapprocher,
# ex. "Wolves" vs "Wolverhampton Wanderers"). Normalisés en minuscules sans
# accents avant comparaison. Liste non exhaustive -- à enrichir au fil des
# REVIEW_UNKNOWN rencontrés lors de la relecture.
KNOWN_ALIASES: dict[str, str] = {
    "wolves": "Wolverhampton Wanderers",
    "spurs": "Tottenham Hotspur",
    "the gunners": "Arsenal",
    "man utd": "Manchester United",
    "man u": "Manchester United",
    "man city": "Manchester City",
    "villa": "Aston Villa",
    "hammers": "West Ham United",
    "saints": "Southampton",
    "boro": "Middlesbrough",
    "wednesday": "Sheffield Wednesday",
    "forest": "Nottingham Forest",
    "gladbach": "Borussia Monchengladbach",
    "bmg": "Borussia Monchengladbach",
    "rb leipzig": "RB Leipzig",
    "rasenballsport leipzig": "RB Leipzig",
    "bayern": "Bayern Munich",
    "psg": "Paris Saint Germain",
    "inter": "Inter Milan",
    "internazionale": "Inter Milan",
    "juve": "Juventus",
    "atleti": "Atletico Madrid",
    "atm": "Atletico Madrid",
    "real": "Real Madrid",
    "barca": "Barcelona",
}

# Suffixes/préfixes fréquents dans les noms de clubs, à ignorer pour le score
# de similarité (mais PAS retirés du nom final écrit dans le YAML).
_NOISE_TOKENS = {
    "fc", "cf", "ac", "as", "ss", "us", "sv", "sc", "cd", "ud", "rc", "afc",
    "calcio", "club", "de", "do", "the",
}


def normalize_for_matching(name: str) -> str:
    """Nom -> forme normalisée pour la comparaison uniquement (le nom
    d'origine, lui, n'est jamais modifié dans les sorties)."""
    text = name.replace("_", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", " ", text).lower()
    tokens = [t for t in text.split() if t not in _NOISE_TOKENS]
    return " ".join(tokens) if tokens else text.strip()


def best_match(name: str, canonical_names: list[str]) -> tuple[str | None, float]:
    """Renvoie (meilleur candidat, score 0-1) parmi canonical_names, ou (None, 0)
    si la liste est vide."""
    if not canonical_names:
        return None, 0.0

    normalized_target = normalize_for_matching(name)
    normalized_candidates = {c: normalize_for_matching(c) for c in canonical_names}

    scored = [
        (canonical, difflib.SequenceMatcher(None, normalized_target, normalized).ratio())
        for canonical, normalized in normalized_candidates.items()
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[0]


def build_draft_mapping(
    foreign_names: set[str], canonical_names: set[str]
) -> tuple[dict[str, str], list[dict]]:
    """Construit un mapping brouillon {nom_source: nom_canonique_proposé}.

    Renvoie (mapping, rapport) où rapport liste, pour les correspondances
    incertaines ou absentes, le détail à vérifier à la main (top candidats
    + score), pour ne pas avoir à deviner pourquoi une entrée est marquée
    à relire.
    """
    canonical_list = sorted(canonical_names)
    mapping: dict[str, str] = {}
    review_report: list[dict] = []

    for name in sorted(foreign_names):
        alias_target = KNOWN_ALIASES.get(normalize_for_matching(name))
        if alias_target is not None:
            # L'alias donne un nom "standard" qui doit encore être rapproché
            # de l'orthographe EXACTE utilisée dans le référentiel canonique
            # (ex. "Bayern Munich" vs "Bayern München" selon la source).
            candidate, score = best_match(alias_target, canonical_list)
            if candidate is not None and score >= AUTO_ACCEPT_THRESHOLD:
                mapping[name] = candidate
                continue
            # Alias connu mais pas de correspondance nette dans CE référentiel
            # (championnat/saison différents) -> on garde le nom standard de
            # l'alias, marqué pour relecture rapide plutôt que UNKNOWN.
            mapping[name] = f"{REVIEW_MARKER}{alias_target}"
            review_report.append(
                {"source_name": name, "best_candidate": alias_target, "score": None, "via_alias": True}
            )
            continue

        candidate, score = best_match(name, canonical_list)

        if candidate is not None and score >= AUTO_ACCEPT_THRESHOLD:
            mapping[name] = candidate
        elif candidate is not None and score >= REVIEW_THRESHOLD:
            mapping[name] = f"{REVIEW_MARKER}{candidate}"
            review_report.append(
                {"source_name": name, "best_candidate": candidate, "score": round(score, 2)}
            )
        else:
            mapping[name] = f"{REVIEW_MARKER}UNKNOWN"
            # Top 3 candidats même faibles, pour aider la relecture manuelle
            normalized_target = normalize_for_matching(name)
            scored_all = sorted(
                (
                    (c, difflib.SequenceMatcher(None, normalized_target, normalize_for_matching(c)).ratio())
                    for c in canonical_list
                ),
                key=lambda pair: pair[1],
                reverse=True,
            )[:3]
            review_report.append(
                {
                    "source_name": name,
                    "best_candidate": None,
                    "score": round(score, 2),
                    "top_candidates": [(c, round(s, 2)) for c, s in scored_all],
                }
            )

    return mapping, review_report
