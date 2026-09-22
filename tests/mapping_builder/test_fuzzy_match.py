"""Tests du rapprochement approximatif de noms d'équipe (`fuzzy_match.py`).

Convertit en assertions réelles l'ancien script d'affichage manuel
`mapping_builder/test_fuzzy_match_synthetic.py`, en réutilisant les mêmes
jeux de données (Premier League / Bundesliga, Understat / API-Football)
pour valider les seuils AUTO_ACCEPT_THRESHOLD / REVIEW_THRESHOLD.
"""
from __future__ import annotations

from foot_predictor.mapping_builder.fuzzy_match import (
    REVIEW_MARKER,
    best_match,
    build_draft_mapping,
    normalize_for_matching,
)

# Référentiel canonique simulé (ce que football-data + son mapping donnerait)
CANONICAL_PREMIER_LEAGUE = {
    "Manchester United", "Manchester City", "Newcastle United", "Tottenham Hotspur",
    "Wolverhampton Wanderers", "Nottingham Forest", "Arsenal", "Chelsea", "Liverpool",
    "Everton", "West Ham United", "Brighton", "Crystal Palace", "Aston Villa",
    "Leicester", "Southampton", "Burnley", "Watford", "Norwich", "Sheffield United",
}

CANONICAL_BUNDESLIGA = {
    "Bayern Munich", "Borussia Dortmund", "RB Leipzig", "Bayer Leverkusen",
    "Borussia Monchengladbach", "VfL Wolfsburg", "Eintracht Frankfurt", "FC Koln",
    "Union Berlin", "Werder Bremen",
}

# Cas Understat (underscores, parfois noms complets différents)
UNDERSTAT_PREMIER_LEAGUE = {
    "Manchester_United", "Manchester_City", "Newcastle_United", "Tottenham",
    "Wolverhampton_Wanderers", "Nottingham_Forest", "Arsenal", "Chelsea", "Liverpool",
    "Everton", "West_Ham", "Brighton", "Crystal_Palace", "Aston_Villa",
    "Leicester", "Southampton", "Burnley", "Watford", "Norwich", "Sheffield_United",
}

UNDERSTAT_BUNDESLIGA = {
    "Bayern_Munich", "Borussia_Dortmund", "RasenBallsport_Leipzig", "Bayer_Leverkusen",
    "Borussia_M.Gladbach", "Wolfsburg", "Eintracht_Frankfurt", "FC_Koln",
    "Union_Berlin", "Werder_Bremen",
}

# Cas API-Football (souvent noms complets, parfois avec accents corrects)
API_FOOTBALL_PREMIER_LEAGUE = {
    "Manchester United", "Manchester City", "Newcastle", "Tottenham",
    "Wolves", "Nottingham Forest", "Arsenal", "Chelsea", "Liverpool",
    "Everton", "West Ham", "Brighton", "Crystal Palace", "Aston Villa",
    "Leicester", "Southampton", "Burnley", "Watford", "Norwich", "Sheffield Utd",
}

API_FOOTBALL_BUNDESLIGA = {
    "Bayern Munchen", "Borussia Dortmund", "RB Leipzig", "Bayer Leverkusen",
    "Borussia Monchengladbach", "Wolfsburg", "Eintracht Frankfurt", "FC Koln",
    "Union Berlin", "Werder Bremen",
}


# ---------------------------------------------------------------------------
# normalize_for_matching / best_match — unités de base
# ---------------------------------------------------------------------------


def test_normalize_for_matching_replaces_underscores_and_strips_accents():
    assert normalize_for_matching("Bayern_München") == "bayern munchen"


def test_normalize_for_matching_drops_noise_tokens():
    assert normalize_for_matching("FC Koln") == "koln"
    assert normalize_for_matching("AC Milan") == "milan"


def test_best_match_returns_none_for_empty_candidate_list():
    candidate, score = best_match("Arsenal", [])
    assert candidate is None
    assert score == 0.0


def test_best_match_perfect_match_after_normalization():
    candidate, score = best_match("Manchester_United", ["Manchester United", "Manchester City"])
    assert candidate == "Manchester United"
    assert score == 1.0


# ---------------------------------------------------------------------------
# build_draft_mapping — jeux de données réalistes (ex-script synthétique)
# ---------------------------------------------------------------------------


def test_understat_premier_league_mostly_auto_accepted():
    mapping, report = build_draft_mapping(UNDERSTAT_PREMIER_LEAGUE, CANONICAL_PREMIER_LEAGUE)

    assert mapping["Arsenal"] == "Arsenal"
    assert mapping["Manchester_United"] == "Manchester United"
    assert mapping["Aston_Villa"] == "Aston Villa"
    assert mapping["Wolverhampton_Wanderers"] == "Wolverhampton Wanderers"

    # "Tottenham" et "West_Ham" sont des abréviations sans recouvrement
    # suffisant avec le nom complet -> marqués à relire, pas auto-acceptés.
    assert mapping["Tottenham"] == f"{REVIEW_MARKER}Tottenham Hotspur"
    assert mapping["West_Ham"] == f"{REVIEW_MARKER}West Ham United"

    n_review = sum(1 for v in mapping.values() if v.startswith(REVIEW_MARKER))
    assert n_review == 2
    assert len(report) == n_review


def test_api_football_premier_league_wolves_alias_auto_accepted():
    mapping, _report = build_draft_mapping(API_FOOTBALL_PREMIER_LEAGUE, CANONICAL_PREMIER_LEAGUE)

    # "Wolves" n'a aucun recouvrement de caractères avec "Wolverhampton
    # Wanderers" : seul KNOWN_ALIASES permet de le rapprocher, auto-accepté
    # car l'alias donne le nom canonique exact.
    assert mapping["Wolves"] == "Wolverhampton Wanderers"

    assert mapping["Newcastle"] == f"{REVIEW_MARKER}Newcastle United"
    assert mapping["Tottenham"] == f"{REVIEW_MARKER}Tottenham Hotspur"
    assert mapping["West Ham"] == f"{REVIEW_MARKER}West Ham United"


def test_understat_bundesliga_alias_and_review_cases():
    mapping, _report = build_draft_mapping(UNDERSTAT_BUNDESLIGA, CANONICAL_BUNDESLIGA)

    # Alias explicite "rasenballsport leipzig" -> nom canonique exact "RB Leipzig".
    assert mapping["RasenBallsport_Leipzig"] == "RB Leipzig"
    assert mapping["Bayern_Munich"] == "Bayern Munich"

    # "Borussia_M.Gladbach" : score insuffisant pour l'auto-acceptation malgré
    # l'alias partiel "gladbach"/"bmg" (le nom source complet n'y correspond
    # pas exactement) -> marqué à relire.
    assert mapping["Borussia_M.Gladbach"] == f"{REVIEW_MARKER}Borussia Monchengladbach"

    # "Wolfsburg" seul ne matche pas assez "VfL Wolfsburg" pour l'auto-accept.
    assert mapping["Wolfsburg"] == f"{REVIEW_MARKER}VfL Wolfsburg"


def test_api_football_bundesliga_close_spelling_auto_accepted():
    mapping, _report = build_draft_mapping(API_FOOTBALL_BUNDESLIGA, CANONICAL_BUNDESLIGA)

    # "Bayern Munchen" (sans tréma) doit rester suffisamment proche de
    # "Bayern Munich" pour l'auto-acceptation malgré l'orthographe différente.
    assert mapping["Bayern Munchen"] == "Bayern Munich"
    assert mapping["Borussia Monchengladbach"] == "Borussia Monchengladbach"

    assert mapping["Wolfsburg"] == f"{REVIEW_MARKER}VfL Wolfsburg"


def test_build_draft_mapping_unknown_name_has_no_overlap_with_canonical():
    mapping, report = build_draft_mapping({"Totally Unknown Club"}, CANONICAL_PREMIER_LEAGUE)

    assert mapping["Totally Unknown Club"] == f"{REVIEW_MARKER}UNKNOWN"
    assert report[0]["source_name"] == "Totally Unknown Club"
    assert report[0]["best_candidate"] is None
    assert len(report[0]["top_candidates"]) == 3
