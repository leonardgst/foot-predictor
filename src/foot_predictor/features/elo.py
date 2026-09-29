"""Elo maison (groupe G1), une échelle par pays, mis à jour **par jour** (ADR-0031).

Fonction pure : `compute_elo(matches, params)` lit une table de matchs (celle de la porte
`features/sources.py`, ou un calendrier à l'inférence) et renvoie, pour chaque match d'une
échelle et chaque équipe, les notes **avant** le match. Aucun accès à la base.

Formules (rapport I.3, ADR-0031) :

- espérance de l'équipe à domicile, avec l'avantage du terrain `H` en points :
  E = 1 / (1 + 10^(−(R_dom + H − R_ext) / 400)) ;
- résultat S = 1 (victoire à domicile), 0,5 (nul), 0 (défaite) ;
- mise à jour, somme nulle : ΔR_dom = K · G · (S − E), ΔR_ext = −ΔR_dom, où G est le
  multiplicateur d'écart de buts de l'Elo des sélections (G = 1 si l'écart N ≤ 1,
  1,5 si N = 2, (11 + N) / 8 si N ≥ 3), ou 1 sans multiplicateur ;
- intersaison : au premier match d'une nouvelle saison, une équipe présente dans l'échelle
  la saison précédente revient vers la moyenne de **sa division de la nouvelle saison** :
  R ← m + (1 − r) · (R − m), où m est la note moyenne de fin de saison précédente des
  équipes de cette division ;
- équipe sans match dans l'échelle la saison précédente (promue de D3, ou absente) : note
  d'entrée = moyenne des 3 plus basses notes de fin de saison de sa division ; la toute
  première saison (2000-01), 1500 en D1 et 1500 − Δ en D2.

Règles temporelles (ADR-0010) : la note d'un match du jour J ne dépend que des matchs
**terminés avant le jour J** ; les matchs d'un même jour ne s'influencent pas (les
variations du jour sont appliquées ensemble, à la fin du jour). Seuls les matchs terminés,
non exclus (ADR-0009) et avec un score au temps réglementaire alimentent l'Elo ; les
autres (à venir, reportés, exclus) reçoivent quand même leurs notes d'avant-match.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import LADDERS

REQUIRED_COLUMNS = (
    "match_id",
    "match_day",
    "season_year",
    "api_league_id",
    "home_team_id",
    "away_team_id",
    "home_goals_90",
    "away_goals_90",
    "status",
    "excluded",
)


@dataclass(frozen=True)
class EloParams:
    """Paramètres de l'Elo. Choisis par la grille de `elo_tuning` (2005-06 à 2014-15), puis figés."""

    k: float = 20.0
    """Facteur K : amplitude d'une mise à jour, en points."""
    home_advantage: float = 60.0
    """Avantage du terrain H, en points, ajouté à la note de l'équipe à domicile dans l'espérance."""
    season_regression: float = 0.2
    """Part r de l'écart à la moyenne de la division retirée à chaque intersaison (0 : aucun retour)."""
    goal_multiplier: bool = True
    """Multiplicateur d'écart de buts G (Elo des sélections) ; sinon G = 1."""
    initial_gap: float = 100.0
    """Écart Δ entre la D1 et la D2 à la toute première saison de chaque échelle."""
    base: float = 1500.0
    scale: float = 400.0
    entry_bottom_n: int = 3
    """Nombre de plus basses notes de fin de saison moyennées pour la note d'entrée."""

    def to_dict(self) -> dict:
        return asdict(self)


def goal_factor(goal_difference: int, enabled: bool = True) -> float:
    """Multiplicateur G de l'Elo des sélections, selon l'écart de buts absolu N."""
    if not enabled:
        return 1.0
    n = abs(int(goal_difference))
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11 + n) / 8


def expected_home(r_home: float, r_away: float, home_advantage: float, scale: float = 400.0) -> float:
    """Espérance de résultat de l'équipe à domicile (probabilité de victoire + moitié du nul)."""
    return 1.0 / (1.0 + 10.0 ** (-(r_home + home_advantage - r_away) / scale))


class _Ladder:
    """État d'une échelle nationale : saison courante et cibles d'intersaison."""

    def __init__(self) -> None:
        self.season: int | None = None
        self.means: dict[int, float] = {}  # niveau -> moyenne de fin de saison précédente
        self.entry: dict[int, float] = {}  # niveau -> note d'entrée


def compute_elo(matches: pd.DataFrame, params: EloParams | None = None) -> pd.DataFrame:
    """Notes d'avant-match, une ligne par (match, équipe), pour les matchs des échelles.

    Colonnes renvoyées : `match_id`, `team_id`, `is_home`, `elo_pre` (note de l'équipe),
    `opp_elo_pre` (note de l'adversaire), `elo_matches` et `opp_elo_matches` (nombre de
    matchs d'échelle déjà joués, depuis 2000-01). L'ordre des lignes d'entrée ne change rien.
    """
    params = params or EloParams()
    missing = [c for c in REQUIRED_COLUMNS if c not in matches.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes pour l'Elo : {missing}")

    frame = matches[matches["api_league_id"].isin(list(LADDERS))].copy()
    frame = frame.sort_values(["match_day", "match_id"], kind="mergesort")

    rating: dict[int, float] = {}
    played: dict[int, int] = {}
    last_season: dict[int, int] = {}  # dernière saison jouée dans l'échelle
    last_level: dict[int, int] = {}  # niveau de cette saison-là
    country_of: dict[int, str] = {}
    ladders: dict[str, _Ladder] = {}
    out: list[tuple] = []

    def open_season(country: str, season: int) -> _Ladder:
        """Premier match de la saison dans l'échelle : fige les cibles d'intersaison."""
        ladder = ladders.setdefault(country, _Ladder())
        if ladder.season is None or season > ladder.season:
            previous = season - 1
            ladder.means, ladder.entry = {}, {}
            for level in (1, 2):
                members = [
                    rating[t]
                    for t, s in last_season.items()
                    if s == previous and last_level[t] == level and country_of[t] == country
                ]
                if members:
                    ladder.means[level] = float(np.mean(members))
                    lowest = sorted(members)[: params.entry_bottom_n]
                    ladder.entry[level] = float(np.mean(lowest))
            ladder.season = season
        return ladder

    def prepare(team: int, country: str, level: int, season: int) -> None:
        """Intersaison ou entrée dans l'échelle, au premier match de la saison de l'équipe."""
        previous = last_season.get(team)
        if previous is not None and season <= previous:
            return  # même saison (ou match tardif d'une saison close) : rien à faire
        ladder = open_season(country, season)
        if previous == season - 1 and team in rating:
            mean = ladder.means.get(level)
            if mean is not None:
                rating[team] = mean + (1.0 - params.season_regression) * (rating[team] - mean)
        elif level in ladder.entry:
            rating[team] = ladder.entry[level]
        else:
            rating[team] = params.base - (params.initial_gap if level == 2 else 0.0)
        last_season[team] = season
        last_level[team] = level
        country_of[team] = country

    # Tableaux extraits une fois : la boucle Python ne touche plus pandas (grille de réglage rapide).
    n = len(frame)
    match_ids = frame["match_id"].to_numpy(dtype=np.int64)
    days = pd.to_datetime(frame["match_day"]).to_numpy(dtype="datetime64[D]").astype(np.int64)
    seasons = frame["season_year"].to_numpy(dtype=np.int64)
    leagues = frame["api_league_id"].to_numpy(dtype=np.int64)
    homes = frame["home_team_id"].to_numpy(dtype=np.int64)
    aways = frame["away_team_id"].to_numpy(dtype=np.int64)
    goals_home = pd.to_numeric(frame["home_goals_90"]).to_numpy(dtype="float64", na_value=np.nan)
    goals_away = pd.to_numeric(frame["away_goals_90"]).to_numpy(dtype="float64", na_value=np.nan)
    updates = (
        (frame["status"] == "played").to_numpy()
        & ~frame["excluded"].astype(bool).to_numpy()
        & ~np.isnan(goals_home)
        & ~np.isnan(goals_away)
    )
    if "round" in frame.columns:
        rounds = frame["round"]
        regular = (rounds.isna() | rounds.fillna("").astype(str).str.startswith("Regular Season")).to_numpy()
    else:
        regular = np.ones(n, dtype=bool)

    pending: list[tuple[int, int, float]] = []

    def apply_pending() -> None:
        """Variations du jour appliquées ensemble : deux matchs du même jour ne s'influencent pas."""
        for home, away, delta in pending:
            rating[home] += delta
            rating[away] -= delta
            played[home] = played.get(home, 0) + 1
            played[away] = played.get(away, 0) + 1
        pending.clear()

    current_day = None
    for i in range(n):
        if days[i] != current_day:
            apply_pending()
            current_day = days[i]
        country, level = LADDERS[int(leagues[i])]
        season = int(seasons[i])
        home, away = int(homes[i]), int(aways[i])
        prepare(home, country, level, season)
        prepare(away, country, level, season)
        # Le niveau d'une saison se lit sur la saison régulière : un barrage de D1 joué par
        # une équipe de D2 ne la range pas en D1 pour les cibles de l'intersaison suivante.
        if regular[i]:
            last_level[home] = last_level[away] = level
        r_home, r_away = rating[home], rating[away]
        n_home, n_away = played.get(home, 0), played.get(away, 0)
        mid = int(match_ids[i])
        out.append((mid, home, True, r_home, r_away, n_home, n_away))
        out.append((mid, away, False, r_away, r_home, n_away, n_home))
        if updates[i]:
            gh, ga = int(goals_home[i]), int(goals_away[i])
            result = 1.0 if gh > ga else 0.5 if gh == ga else 0.0
            expected = expected_home(r_home, r_away, params.home_advantage, params.scale)
            delta = params.k * goal_factor(gh - ga, params.goal_multiplier) * (result - expected)
            pending.append((home, away, delta))
    apply_pending()

    columns = ["match_id", "team_id", "is_home", "elo_pre", "opp_elo_pre", "elo_matches", "opp_elo_matches"]
    result = pd.DataFrame(out, columns=columns)
    if not result.empty:
        assert all(math.isfinite(v) for v in result["elo_pre"])
    return result.astype({"match_id": "Int64", "team_id": "Int64", "elo_matches": "Int64", "opp_elo_matches": "Int64"})
