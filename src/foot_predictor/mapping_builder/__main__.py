"""Brouillons des YAML de rapprochement, produits par du code reproductible (partie 2, 2.5).

    python -m foot_predictor.mapping_builder teams --raw-dir C:/foot-predictor/data/raw --external-raw-dir data/raw
    python -m foot_predictor.mapping_builder player-aliases --raw-dir C:/foot-predictor/data/raw

Chaque commande **réécrit** le fichier de `ingestion/mappings/` concerné : la
relecture se fait sur le diff Git, avant le commit. Le brut est lu en lecture
seule. Seuls des nombres et des noms d'équipes sont affichés.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from foot_predictor.ingestion.yaml_mappings import MAPPINGS_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.mapping_builder")
    parser.add_argument("--raw-dir", type=Path, required=True, help="brut API-FOOTBALL (lecture seule)")
    parser.add_argument("--output-dir", type=Path, default=MAPPINGS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    teams = sub.add_parser("teams", help="équipes football-data -> team.id API")
    teams.add_argument("--external-raw-dir", type=Path, required=True, help="bruts externes (CSV football-data)")
    sub.add_parser("player-aliases", help="doublons de joueurs -> identifiant principal")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if args.command == "teams":
        from foot_predictor.mapping_builder import team_ids

        draft = team_ids.build(args.raw_dir, args.external_raw_dir)
        target = args.output_dir / "football_data_team_ids.yaml"
        target.write_text(team_ids.to_yaml(draft), encoding="utf-8")
        matched = sum(m for m, _ in draft.per_season.values())
        unmatched = sum(u for _, u in draft.per_season.values())
        print(f"Saisons couvertes par l'API : {len(draft.per_season)} ; appariements équipe-saison : {matched}, "
              f"non appariés : {unmatched}")  # fmt: skip
        print(f"Noms : {len(draft.teams)} appariés, {len(draft.hors_api)} hors API, "
              f"{len(draft.non_apparies)} non appariés (listés) -> {target}")  # fmt: skip
        return 0
    from foot_predictor.mapping_builder import player_aliases

    draft = player_aliases.build(args.raw_dir)
    target = args.output_dir / "player_aliases.yaml"
    target.write_text(player_aliases.to_yaml(draft), encoding="utf-8")
    print(f"Groupes de doublons : {draft.groups} ; retenus : {draft.retained} ; douteux (hors YAML) : "
          f"{draft.doubtful} ; alias écrits : {len(draft.aliases)} -> {target}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
