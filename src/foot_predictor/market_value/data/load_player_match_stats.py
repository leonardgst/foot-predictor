"""
Chargement de la fenêtre glissante des N derniers matchs joués par chaque
joueur, pour un groupe de poste donné, avant une date de référence
`as_of_date` (cf. recap clustering, section 5 : anti-fuite temporelle
stricte du projet -> on n'utilise jamais un match dont match_date >= as_of_date).

⚠️ La fenêtre est par JOUEUR (les 50 derniers matchs DE CE JOUEUR), pas un
LIMIT 50 global sur la requête -> on utilise une window function SQL
(ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY match_date DESC)).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Match, PlayerMatchStats

# Colonnes réellement disponibles dans staging.player_match_stats
# (cf. recap clustering, section 2 - ne pas en supposer d'autres).
STATS_COLUMNS = [
    "minutes",
    "rating",
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "key_passes",
    "pass_accuracy_pct",
    "tackles",
    "interceptions",
    "duels_total",
    "duels_won",
    "dribbles_attempts",
    "dribbles_success",
    "dribbled_past",
    "fouls_drawn",
    "fouls_committed",
    "yellow_cards",
    "red_cards",
    "xg",
    "xa",
    "npxg",
]


def load_player_match_stats_window(
    session: Session,
    position_bucket: str,
    as_of_date: dt.date,
    window_size: int = 50,
) -> pd.DataFrame:
    """Renvoie un DataFrame une ligne par (player_id, match_id), limité aux
    `window_size` derniers matchs de chaque joueur avant `as_of_date`, pour
    le groupe de poste `position_bucket`.

    Colonnes : player_id, match_id, match_date, + toutes les STATS_COLUMNS.
    """
    row_number = (
        func.row_number()
        .over(
            partition_by=PlayerMatchStats.player_id,
            order_by=Match.match_date.desc(),
        )
        .label("rn")
    )

    ranked = (
        select(
            PlayerMatchStats.player_id,
            PlayerMatchStats.match_id,
            Match.match_date,
            *[getattr(PlayerMatchStats, col) for col in STATS_COLUMNS],
            row_number,
        )
        .join(Match, Match.id == PlayerMatchStats.match_id)
        .where(
            PlayerMatchStats.position_bucket == position_bucket,
            Match.match_date < as_of_date,
        )
        .subquery()
    )

    stmt = select(ranked).where(ranked.c.rn <= window_size)
    rows = session.execute(stmt).all()

    columns = ["player_id", "match_id", "match_date", *STATS_COLUMNS, "rn"]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return df
    return df.drop(columns=["rn"])
