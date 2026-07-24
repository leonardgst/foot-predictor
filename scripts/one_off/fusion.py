"""Fusion des équipes dupliquées (brut vs canonique).
Lance d'abord en dry-run (DRY_RUN=True) pour vérifier, puis repasse à False."""
import yaml
from pathlib import Path
from sqlalchemy import select, func, update, delete
from foot_predictor.db.session import get_session
from foot_predictor.db.models import Team, Match, TeamMatch, TeamSourceMapping

DRY_RUN = False  # <-- passer à False une fois le dry-run validé

MAPPING_PATH = Path("src/foot_predictor/ingestion/mappings/football_data_teams.yaml")
mapping = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))

def count_refs(session, team_id):
    n_match = session.scalar(
        select(func.count()).select_from(Match).where(
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id)
        )
    )
    n_tm = session.scalar(select(func.count()).select_from(TeamMatch).where(TeamMatch.team_id == team_id))
    return n_match + n_tm

with get_session() as session:
    n_merged = 0
    for raw_code, canonical in mapping.items():
        raw_team = session.scalar(select(Team).where(Team.name == raw_code))
        canon_team = session.scalar(select(Team).where(Team.name == canonical))
        if raw_team is None or canon_team is None or raw_team.id == canon_team.id:
            continue

        raw_refs = count_refs(session, raw_team.id)
        canon_refs = count_refs(session, canon_team.id)

        if raw_refs > 0 and canon_refs > 0:
            print(f"⚠️  CONFLIT RÉEL (les deux ont des données) : {raw_code!r} vs {canonical!r} -- SKIP, à traiter à la main")
            continue

        keep_id, drop_id = (raw_team.id, canon_team.id) if raw_refs >= canon_refs else (canon_team.id, raw_team.id)

        print(f"{raw_code!r} (id={raw_team.id}) <-> {canonical!r} (id={canon_team.id}) "
              f":: garde id={keep_id}, supprime id={drop_id}, renomme en {canonical!r}")

        if not DRY_RUN:
            session.execute(
                update(TeamSourceMapping).where(TeamSourceMapping.team_id == drop_id).values(team_id=keep_id)
            )
            session.execute(delete(Team).where(Team.id == drop_id))
            session.execute(update(Team).where(Team.id == keep_id).values(name=canonical))
        n_merged += 1

    if DRY_RUN:
        print(f"\n[DRY RUN] {n_merged} fusion(s) seraient effectuées. Repasse DRY_RUN=False pour appliquer.")
    else:
        session.commit()
        print(f"\n{n_merged} fusion(s) appliquée(s) et commitées.")