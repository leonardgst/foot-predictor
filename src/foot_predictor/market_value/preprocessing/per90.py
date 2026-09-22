"""
Agrégation des lignes player_match_stats (une par match) en un vecteur par
joueur, sur la fenêtre glissante déjà filtrée par load_player_match_stats_window.

Règles (cf. recap clustering, sections 3 et 6) :
- Une ligne de match n'est incluse dans l'agrégation que si minutes >= MIN_MINUTES_PER_MATCH.
- Les stats comptées sont converties en valeur par 90 minutes : sum(stat) * 90 / sum(minutes).
- Les stats déjà en ratio (pass_accuracy_pct, duels_won_pct) sont moyennées, pondérées par les minutes.
- xg/xa/npxg : NULL exclu ligne par ligne du calcul (pas toute la ligne rejetée).
  Un joueur avec trop de matchs sans xG est signalé via *_coverage plutôt que
  d'être arbitrairement mis à 0 (ce qui fausserait le clustering).

Seuils ajustables une fois les diagnostics (data/diagnostics.py) lancés sur
les vraies données.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_MINUTES_PER_MATCH = 20
MIN_MATCHES_IN_WINDOW = 15  # garde-fou anti-bruit, cf. recap section 5

COUNTING_STATS = [
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "key_passes",
    "tackles",
    "interceptions",
    "dribbles_attempts",
    "dribbles_success",
    "dribbled_past",
    "fouls_drawn",
    "fouls_committed",
]

# Stats traitées à part car souvent NULL (Understat pas encore ingéré pour ce match).
XG_STATS = ["xg", "xa", "npxg"]

# nom de sortie -> (numérateur, dénominateur), déjà présents dans les colonnes brutes
RATIO_STATS = {
    "duels_won_pct": ("duels_won", "duels_total"),
}


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def build_player_vectors(df: pd.DataFrame) -> pd.DataFrame:
    """df : sortie de load_player_match_stats_window (une ligne par match).
    Retourne un DataFrame une ligne par player_id, indexé sur player_id, avec
    les colonnes *_per90, les ratios, la couverture xG (*_coverage) et
    matches_in_window (nombre total de matchs dans la fenêtre, AVANT filtre
    minutes >= 20, pour appliquer le seuil minimum de section 5)."""
    if df.empty:
        return pd.DataFrame()

    total_matches = df.groupby("player_id").size().rename("matches_in_window")
    eligible = df[df["minutes"] >= MIN_MINUTES_PER_MATCH].copy()

    rows = []
    for player_id, group in eligible.groupby("player_id"):
        minutes_sum = group["minutes"].sum()
        record = {"player_id": player_id, "matches_in_window": int(total_matches.loc[player_id])}

        if minutes_sum <= 0:
            record["eligible_minutes_sum"] = 0
            rows.append(record)
            continue

        record["eligible_minutes_sum"] = float(minutes_sum)

        for stat in COUNTING_STATS:
            record[f"{stat}_per90"] = group[stat].fillna(0).sum() * 90 / minutes_sum

        for out_name, (num_col, denom_col) in RATIO_STATS.items():
            num = group[num_col].fillna(0).sum()
            denom = group[denom_col].fillna(0).sum()
            record[out_name] = (num / denom) if denom > 0 else np.nan

        record["pass_accuracy_pct"] = _weighted_mean(group["pass_accuracy_pct"], group["minutes"])

        for stat in XG_STATS:
            non_null = group[stat].notna()
            record[f"{stat}_coverage"] = float(non_null.mean())
            if non_null.any():
                minutes_with_stat = group.loc[non_null, "minutes"].sum()
                record[f"{stat}_per90"] = (
                    group.loc[non_null, stat].sum() * 90 / minutes_with_stat
                    if minutes_with_stat > 0
                    else np.nan
                )
            else:
                record[f"{stat}_per90"] = np.nan

        rows.append(record)

    result = pd.DataFrame(rows).set_index("player_id")
    return result


def apply_minimum_sample_filter(
    vectors: pd.DataFrame, min_matches: int = MIN_MATCHES_IN_WINDOW
) -> pd.DataFrame:
    """Ne garde que les joueurs avec assez d'historique dans la fenêtre.
    Les joueurs en-dessous du seuil ne doivent PAS être scorés (cf. recap
    clustering, section 5, garde-fou)."""
    if vectors.empty:
        return vectors
    return vectors[vectors["matches_in_window"] >= min_matches].copy()
