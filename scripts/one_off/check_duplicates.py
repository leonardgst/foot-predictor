"""Diagnostic (lecture seule) : détecte les paires (nom brut / nom canonique)
qui existent TOUTES LES DEUX comme staging.team distincts."""
import yaml
from pathlib import Path
from sqlalchemy import select, func
from foot_predictor.db.session import get_session
from foot_predictor.db.models import Team, Match, TeamMatch

MAPPING_PATH = Path("src/foot_predictor/ingestion/mappings/football_data_teams.yaml")
mapping = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))

def count_refs(session, team_id):
    n_match = session.scalar(
        select(func.count()).select_from(Match).where(
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id)
        )
    )
    n_tm = session.scalar(select(func.count()).select_from(TeamMatch).where(TeamMatch.team_id == team_id))
    return n_match, n_tm

with get_session() as session:
    found = 0
    for raw_code, canonical in mapping.items():
        raw_team = session.scalar(select(Team).where(Team.name == raw_code))
        canon_team = session.scalar(select(Team).where(Team.name == canonical))
        if raw_team is None or canon_team is None or raw_team.id == canon_team.id:
            continue
        found += 1
        n_match_raw, n_tm_raw = count_refs(session, raw_team.id)
        n_match_canon, n_tm_canon = count_refs(session, canon_team.id)
        print(f"\n=== {raw_code!r} (id={raw_team.id}) vs {canonical!r} (id={canon_team.id}) ===")
        print(f"  brut      : {n_match_raw} matchs, {n_tm_raw} team_match")
        print(f"  canonique : {n_match_canon} matchs, {n_tm_canon} team_match")
    print(f"\n{found} doublon(s) détecté(s) au total.")