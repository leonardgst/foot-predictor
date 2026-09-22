"""
Script principal : collecte les noms d'équipe des 3 sources (football-data,
Understat, API-Football) sur 10 saisons, calcule le référentiel canonique
(football-data + son mapping existant), propose des correspondances par
fuzzy matching, et écrit deux fichiers YAML brouillons à relire :

    mappings/understat_teams.yaml      (brouillon)
    mappings/api_football_teams.yaml   (brouillon)

Toutes les entrées incertaines sont préfixées "REVIEW_" (cf. fuzzy_match.py)
-- chercher ce préfixe pour trouver rapidement ce qu'il reste à corriger à
la main avant d'utiliser ces fichiers en production. Un rapport texte détaillé
(candidats + scores) est aussi affiché pour chaque cas ambigu.

Usage :
    python -m foot_predictor.mapping_builder.build_draft_mappings
"""
from __future__ import annotations

from pathlib import Path

import yaml
from understatapi import UnderstatClient

from foot_predictor.mapping_builder.collect_api_football_teams import (
    collect_api_football_team_names,
)
from foot_predictor.mapping_builder.collect_football_data_teams import (
    collect_football_data_team_names,
)
from foot_predictor.mapping_builder.collect_understat_teams import collect_understat_team_names
from foot_predictor.mapping_builder.fuzzy_match import build_draft_mapping

START_YEARS = range(2015, 2025)
CORRESPONDENCE_PATH = Path(__file__).parent / "leagues_correspondence.yaml"
# mappings/ est sous foot_predictor/ingestion/mappings/ (cf. common.py :
# MAPPINGS_DIR = Path(__file__).parent / "mappings", et common.py est dans
# foot_predictor/ingestion/) -- PAS directement sous foot_predictor/.
FOOTBALL_DATA_TEAMS_MAPPING_PATH = (
    Path(__file__).parent.parent / "ingestion" / "mappings" / "football_data_teams.yaml"
)
OUTPUT_DIR = Path(__file__).parent / "draft_output"


def _load_existing_football_data_mapping() -> dict[str, str]:
    if not FOOTBALL_DATA_TEAMS_MAPPING_PATH.exists():
        print(
            f"⚠️  ATTENTION : {FOOTBALL_DATA_TEAMS_MAPPING_PATH} introuvable -- le "
            f"référentiel canonique va utiliser les codes bruts football-data "
            f"(ex. 'Man City' au lieu de 'Manchester City'). Vérifier le chemin."
        )
        return {}
    mapping = yaml.safe_load(FOOTBALL_DATA_TEAMS_MAPPING_PATH.read_text(encoding="utf-8")) or {}
    print(f"Mapping football_data_teams.yaml chargé : {len(mapping)} entrées ({FOOTBALL_DATA_TEAMS_MAPPING_PATH})")
    return mapping


def _canonical_names_for_division(raw_names: set[str], existing_mapping: dict[str, str]) -> set[str]:
    """Applique le mapping football_data_teams.yaml existant : un nom déjà
    mappé donne sa valeur canonique, un nom absent du mapping EST déjà
    canonique par convention du projet (cf. commentaire en tête du YAML)."""
    return {existing_mapping.get(name, name) for name in raw_names}


def build_all_drafts() -> None:
    correspondence = yaml.safe_load(CORRESPONDENCE_PATH.read_text(encoding="utf-8"))
    existing_fd_mapping = _load_existing_football_data_mapping()

    print("=== Collecte football-data (référentiel canonique) ===")
    fd_names_by_div = collect_football_data_team_names(START_YEARS)

    print("\n=== Collecte Understat ===")
    with UnderstatClient() as client:
        us_names_by_league = collect_understat_team_names(client, START_YEARS)

    print("\n=== Collecte API-Football ===")
    league_ids_by_code = {code: info["api_football_league_id"] for code, info in correspondence.items()}
    af_names_by_league = collect_api_football_team_names(START_YEARS, league_ids_by_code)

    understat_mapping: dict[str, str] = {}
    api_football_mapping: dict[str, str] = {}
    full_review_report: list[dict] = []

    for div, info in correspondence.items():
        canonical = _canonical_names_for_division(fd_names_by_div.get(div, set()), existing_fd_mapping)

        us_code = info["understat_league_code"]
        us_mapping, us_report = build_draft_mapping(us_names_by_league.get(us_code, set()), canonical)
        understat_mapping.update(us_mapping)
        for entry in us_report:
            entry["division"] = div
            entry["source"] = "understat"
        full_review_report.extend(us_report)

        af_mapping, af_report = build_draft_mapping(af_names_by_league.get(div, set()), canonical)
        api_football_mapping.update(af_mapping)
        for entry in af_report:
            entry["division"] = div
            entry["source"] = "api-football"
        full_review_report.extend(af_report)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_yaml_draft(OUTPUT_DIR / "understat_teams.yaml", understat_mapping)
    _write_yaml_draft(OUTPUT_DIR / "api_football_teams.yaml", api_football_mapping)
    _print_review_report(full_review_report)

    n_review = sum(1 for v in {**understat_mapping, **api_football_mapping}.values() if v.startswith("REVIEW_"))
    n_total = len(understat_mapping) + len(api_football_mapping)
    print(f"\n{n_total} entrées écrites au total, dont {n_review} à relire manuellement (préfixe REVIEW_).")
    print(f"Fichiers écrits dans {OUTPUT_DIR}/ -- à relire puis copier dans mappings/ une fois corrigés.")


def _write_yaml_draft(path: Path, mapping: dict[str, str]) -> None:
    header = (
        "# BROUILLON généré automatiquement par mapping_builder -- À RELIRE avant usage.\n"
        "# Toute valeur préfixée REVIEW_ est incertaine ou introuvable :\n"
        "#   REVIEW_<nom>    -> meilleure correspondance trouvée mais score insuffisant, à confirmer\n"
        "#   REVIEW_UNKNOWN  -> aucune correspondance plausible, à renseigner à la main\n"
        "# Une fois toutes les entrées REVIEW_ corrigées, retirer ce commentaire et\n"
        "# déplacer ce fichier dans mappings/.\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(mapping, f, allow_unicode=True, sort_keys=True)


def _print_review_report(report: list[dict]) -> None:
    if not report:
        print("\nAucune entrée à relire -- tout a été auto-accepté avec un score suffisant.")
        return

    print(f"\n=== {len(report)} entrées à relire ===")
    for entry in report:
        if "top_candidates" in entry:
            candidates = ", ".join(f"{c} ({s})" for c, s in entry["top_candidates"])
            print(
                f"[{entry['source']}/{entry['division']}] {entry['source_name']!r} "
                f"-> AUCUNE correspondance fiable. Candidats les plus proches : {candidates or 'aucun'}"
            )
        else:
            print(
                f"[{entry['source']}/{entry['division']}] {entry['source_name']!r} "
                f"-> proposé : {entry['best_candidate']!r} (score {entry['score']})"
            )


if __name__ == "__main__":
    build_all_drafts()