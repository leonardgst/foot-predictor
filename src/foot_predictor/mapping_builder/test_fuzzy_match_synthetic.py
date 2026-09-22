"""
Test local du fuzzy matching sur des cas réalistes et difficiles, sans
réseau (les vraies collectes nécessitent football-data.co.uk / Understat /
api-sports.io, indisponibles depuis ce sandbox). Sert à valider les seuils
AUTO_ACCEPT_THRESHOLD / REVIEW_THRESHOLD avant de lancer la vraie collecte.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fuzzy_match import build_draft_mapping  # noqa: E402

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


def run_case(label: str, foreign_names: set[str], canonical_names: set[str]) -> None:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    mapping, report = build_draft_mapping(foreign_names, canonical_names)
    for source_name in sorted(mapping):
        marker = "  <-- À RELIRE" if mapping[source_name].startswith("REVIEW_") else ""
        print(f"  {source_name!r:35} -> {mapping[source_name]!r}{marker}")

    n_review = sum(1 for v in mapping.values() if v.startswith("REVIEW_"))
    print(f"\n{len(mapping)} entrées, {n_review} à relire ({n_review / len(mapping):.0%})")


if __name__ == "__main__":
    run_case("Understat -> Premier League canonique", UNDERSTAT_PREMIER_LEAGUE, CANONICAL_PREMIER_LEAGUE)
    run_case("API-Football -> Premier League canonique", API_FOOTBALL_PREMIER_LEAGUE, CANONICAL_PREMIER_LEAGUE)
    run_case("Understat -> Bundesliga canonique", UNDERSTAT_BUNDESLIGA, CANONICAL_BUNDESLIGA)
    run_case("API-Football -> Bundesliga canonique", API_FOOTBALL_BUNDESLIGA, CANONICAL_BUNDESLIGA)
