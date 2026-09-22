"""Construction de la matrice (X, y) pour la prédiction du score exact.

Traduction directe de docs/MODELE_MATHEMATIQUE.md section 2 : pour chaque match
joué, on produit DEUX observations (une par équipe), chacune portant le bloc de
features de l'équipe elle-même ("own_*") ET le bloc de features de son
adversaire DANS CE MÊME MATCH ("opp_*"), l'indicatrice terrain `is_home`, et un
one-hot du championnat (une modalité de référence absorbée, comme x_i en 2.3).

Anti-fuite : les deux blocs proviennent de `features.team_match_features`, déjà
calculée en amont avec un ancrage `as_of_date = match_date` strict (voir
`features/rolling_form.py`, `rolling_xg.py`, `standing.py`). Le seul risque de
fuite propre à CE module serait de joindre par erreur les features d'un autre
match du même adversaire (par ex. sa ligne la plus récente, plutôt que sa ligne
pour CE match précis) -- d'où la jointure explicite sur `match_id` des deux
côtés dans `_index_by_match`, et le test dédié dans tests/modeling/test_dataset.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Competition, Match, TeamMatch, TeamMatchFeatures
from foot_predictor.modeling.features_config import DEFAULT_FEATURE_COLUMNS

OWN_PREFIX = "own_"
OPP_PREFIX = "opp_"
COMPETITION_PREFIX = "comp_"


@dataclass(frozen=True)
class DatasetResult:
    X: pd.DataFrame
    """Colonnes : own_<feature>, opp_<feature> (pour chaque feature_columns),
    is_home, comp_<championnat> (one-hot, une modalité de référence exclue)."""

    y: pd.Series
    """Buts marqués par l'équipe de la ligne (team_match.goals_for)."""

    meta: pd.DataFrame
    """match_id, team_id, opponent_team_id, match_date, competition, is_home --
    pour le split chronologique et le regroupement par match (section 2.4)."""

    n_matches_dropped_missing_features: int
    """Matchs écartés faute de team_match_features pour un des deux côtés."""

    n_rows_dropped_missing_values: int
    """Lignes écartées car au moins une feature (own ou opp) valait NULL --
    essentiellement les tout premiers matchs d'une équipe dans une compétition,
    où les fenêtres glissantes n'ont pas encore assez d'historique."""


def _index_by_match(
    rows: list[tuple[Match, TeamMatch, TeamMatchFeatures, str]],
) -> dict[int, dict[int, tuple[TeamMatch, TeamMatchFeatures]]]:
    """Regroupe (team_match, features) par match_id puis team_id, pour pouvoir
    retrouver, pour un match donné, le bloc de l'adversaire DANS CE MATCH --
    jamais une autre ligne de cet adversaire calculée à une autre date."""
    by_match: dict[int, dict[int, tuple[TeamMatch, TeamMatchFeatures]]] = {}
    for _match, team_match, features, _comp_name in rows:
        by_match.setdefault(team_match.match_id, {})[team_match.team_id] = (team_match, features)
    return by_match


def build_dataset(
    session: Session,
    feature_columns: list[str] | None = None,
    reference_competition: str | None = None,
) -> DatasetResult:
    """Construit (X, y) sur tous les matchs joués disposant de features des
    DEUX côtés. `feature_columns` est un paramètre explicite (défaut : z1-z8,
    cf. features_config.py) -- ajouter z9-z11 plus tard se fait en changeant
    cette liste, pas le code ci-dessous."""
    feature_columns = list(feature_columns or DEFAULT_FEATURE_COLUMNS)

    rows = session.execute(
        select(Match, TeamMatch, TeamMatchFeatures, Competition.name)
        .join(TeamMatch, TeamMatch.match_id == Match.id)
        .join(TeamMatchFeatures, TeamMatchFeatures.team_match_id == TeamMatch.id)
        .join(Competition, Competition.id == Match.competition_id)
        .where(Match.status == "played")
    ).all()

    by_match = _index_by_match(rows)
    match_lookup = {match.id: match for match, *_ in rows}
    comp_name_lookup = {match.id: comp_name for match, _tm, _f, comp_name in rows}

    records: list[dict] = []
    n_matches_dropped = 0
    for match_id, sides in by_match.items():
        match = match_lookup[match_id]
        home_side = sides.get(match.home_team_id)
        away_side = sides.get(match.away_team_id)
        if home_side is None or away_side is None:
            n_matches_dropped += 1
            continue

        home_tm, home_feat = home_side
        away_tm, away_feat = away_side
        competition = comp_name_lookup[match_id]

        records.append(
            _build_row(
                team_match=home_tm,
                own_features=home_feat,
                opp_features=away_feat,
                opponent_team_id=match.away_team_id,
                is_home=True,
                match=match,
                competition=competition,
                feature_columns=feature_columns,
            )
        )
        records.append(
            _build_row(
                team_match=away_tm,
                own_features=away_feat,
                opp_features=home_feat,
                opponent_team_id=match.home_team_id,
                is_home=False,
                match=match,
                competition=competition,
                feature_columns=feature_columns,
            )
        )

    columns = (
        ["match_id", "team_id", "opponent_team_id", "match_date", "competition", "is_home", "y"]
        + [f"{OWN_PREFIX}{c}" for c in feature_columns]
        + [f"{OPP_PREFIX}{c}" for c in feature_columns]
    )
    frame = pd.DataFrame.from_records(records, columns=columns)

    feature_cols = [f"{OWN_PREFIX}{c}" for c in feature_columns] + [
        f"{OPP_PREFIX}{c}" for c in feature_columns
    ]

    # Modalités de championnat et référence déterminées AVANT le dropna, pour
    # que les colonnes one-hot restent stables même si toutes les lignes d'une
    # compétition venaient à être écartées (frame vide notamment).
    all_competitions = sorted(frame["competition"].dropna().unique())
    reference = reference_competition or (all_competitions[0] if all_competitions else None)
    dummies_all = pd.get_dummies(frame["competition"], prefix=COMPETITION_PREFIX.rstrip("_")).astype(float)
    reference_col = f"{COMPETITION_PREFIX.rstrip('_')}_{reference}"
    dummies_all = dummies_all.drop(columns=[reference_col], errors="ignore")

    frame = pd.concat([frame, dummies_all], axis=1)

    n_rows_before = len(frame)
    frame = frame.dropna(subset=feature_cols + ["y"]).reset_index(drop=True)
    n_rows_dropped = n_rows_before - len(frame)

    dummy_cols = list(dummies_all.columns)

    X = pd.concat(
        [
            frame[feature_cols].astype(float),
            frame[["is_home"]].astype(float),
            frame[dummy_cols],
        ],
        axis=1,
    )
    y = frame["y"].astype(int)
    meta = frame[["match_id", "team_id", "opponent_team_id", "match_date", "competition", "is_home"]]

    return DatasetResult(
        X=X,
        y=y,
        meta=meta,
        n_matches_dropped_missing_features=n_matches_dropped,
        n_rows_dropped_missing_values=n_rows_dropped,
    )


def _build_row(
    *,
    team_match: TeamMatch,
    own_features: TeamMatchFeatures,
    opp_features: TeamMatchFeatures,
    opponent_team_id: int,
    is_home: bool,
    match: Match,
    competition: str,
    feature_columns: list[str],
) -> dict:
    row: dict = {
        "match_id": match.id,
        "team_id": team_match.team_id,
        "opponent_team_id": opponent_team_id,
        "match_date": match.match_date,
        "competition": competition,
        "is_home": is_home,
        "y": team_match.goals_for,
    }
    for col in feature_columns:
        row[f"{OWN_PREFIX}{col}"] = getattr(own_features, col)
        row[f"{OPP_PREFIX}{col}"] = getattr(opp_features, col)
    return row
