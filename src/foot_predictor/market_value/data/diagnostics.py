"""
Diagnostics à lancer AVANT d'ajuster définitivement les seuils du pipeline
clustering/MVS (seuil minimum de matchs, choix d'algorithme, gestion des NULL
xG). Conditionne plusieurs décisions listées comme "à trancher une fois les
données réelles chargées" (cf. recap clustering, section 9).

Usage :
    python -m foot_predictor.market_value.data.diagnostics
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy.orm import Session

from foot_predictor.market_value.data.load_player_match_stats import (
    load_player_match_stats_window,
)

POSITION_BUCKETS = ["Defender", "Midfielder", "Attacker"]


def run_diagnostics(session: Session, as_of_date: dt.date, window_size: int = 50) -> dict:
    report = {}
    for bucket in POSITION_BUCKETS:
        df = load_player_match_stats_window(session, bucket, as_of_date, window_size)

        if df.empty:
            report[bucket] = {"n_players": 0, "n_rows": 0}
            continue

        matches_per_player = df.groupby("player_id").size()

        report[bucket] = {
            "n_players": int(df["player_id"].nunique()),
            "n_rows": int(len(df)),
            "matches_per_player_median": float(matches_per_player.median()),
            "matches_per_player_p10": float(matches_per_player.quantile(0.10)),
            "pct_players_with_lt_15_matches": float((matches_per_player < 15).mean()),
            "xg_null_rate": float(df["xg"].isna().mean()),
            "xa_null_rate": float(df["xa"].isna().mean()),
            "npxg_null_rate": float(df["npxg"].isna().mean()),
        }
    return report


def print_report(report: dict) -> None:
    for bucket, stats in report.items():
        print(f"\n=== {bucket} ===")
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    TODAY = dt.date.today()

    with get_session() as session:
        report = run_diagnostics(session, TODAY)
        print_report(report)
