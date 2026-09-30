"""Construction du contexte d'inférence à partir de la base de travail (ADR-0040).

- **Table des matchs** : par la porte `features/sources.load_matches` (scellé filtré en SQL).
- **Version des données** : dernier chargement réussi de `staging` (`ops.load_run`) ; elle change
  la clé du cache des lignes, jamais une ligne périmée n'est servie.
- **Fraîcheur** de `staging` : dernier jour dont tous les matchs terminés sont connus.
- **Noms** des équipes et des championnats : modèles ORM `Team` et `Competition` (aucune lecture
  de la table des matchs hors de la porte).
- **Cotes de référence** : `modeling.models.market` (porte `load_odds`, scellé filtré).
- **Jeu de données** versionné : pour entraîner à la demande les modèles de rejeu.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import select, text

from foot_predictor.inference.availability import Freshness
from foot_predictor.inference.predict import InferenceContext

DATASET_VERSION = "ds-2026-09-30-ba2b91f7"


def last_load_run(engine) -> tuple[int | None, dt.datetime | None]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, finished_at FROM ops.load_run WHERE status = 'ok' ORDER BY id DESC LIMIT 1")
        ).first()
    return (row[0], row[1]) if row else (None, None)


def staging_freshness(matches: pd.DataFrame, last_update: dt.datetime | None) -> Freshness:
    """`staging` est complète jusqu'au dernier jour où un match terminé est connu (rejeu : toujours à jour)."""
    played = matches.loc[matches["status"] == "played", "match_day"]
    return Freshness("staging", max(played) if len(played) else dt.date(1900, 1, 1), last_update)


def names(engine) -> tuple[dict[int, str], dict[int, str]]:
    from sqlalchemy.orm import Session

    from foot_predictor.db.models import Competition, Team

    with Session(engine) as session:
        teams = dict(session.execute(select(Team.id, Team.name)).all())
        competitions = dict(session.execute(select(Competition.id, Competition.name)).all())
    return teams, competitions


def build_context(engine=None, with_odds: bool = True, today: dt.date | None = None) -> InferenceContext:
    from foot_predictor.features.sources import load_dataset, load_matches

    if engine is None:
        from foot_predictor.db.session import get_engine

        engine = get_engine()
    matches = load_matches(engine)
    run_id, finished = last_load_run(engine)
    teams, competitions = names(engine)
    odds = None
    if with_odds:
        from foot_predictor.modeling.models.market import load_market_probabilities

        odds = load_market_probabilities()
    dataset, _ = load_dataset(DATASET_VERSION)
    return InferenceContext(
        matches=matches,
        data_version=f"load_run-{run_id}",
        freshness=staging_freshness(matches, finished),
        team_names=teams,
        competition_names=competitions,
        odds=odds,
        dataset=dataset,
        today=today or dt.datetime.now(dt.UTC).date(),
    )
