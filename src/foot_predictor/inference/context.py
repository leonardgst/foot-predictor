"""Construction du contexte d'inférence à partir de la base de travail (ADR-0040).

- **Table des matchs** : par la porte `features/sources.load_matches`. Avant le test scellé H1, le
  scellé y est filtré en SQL ; une fois le test terminé, la porte l'ouvre à l'inférence, comme
  historique des variables (`opened_for_inference`, ADR-0045). Les cotes restent fermées.
- **Version des données** : dernier chargement réussi de `staging` (`ops.load_run`) ; elle change
  la clé du cache des lignes, jamais une ligne périmée n'est servie.
- **Fraîcheur** de `staging` : dernier jour dont tous les matchs terminés sont connus.
- **Noms** des équipes et des championnats : modèles ORM `Team` et `Competition` (aucune lecture
  de la table des matchs hors de la porte).
- **Cotes de référence** : `modeling.models.market` (porte `load_odds`, scellé filtré).
- **Compositions** (horizon H2, rejeu) : `load_lineups` et `load_team_sheets` de la porte, lues à la
  première demande H2 seulement (tables lourdes) ; le scellé reste filtré en SQL, sans ouverture à
  l'inférence : H2 n'a pas de live (ADR-0010) et le rejeu des saisons scellées reste fermé (ADR-0045).
- **Jeu de données** versionné : pour entraîner à la demande les modèles de rejeu.
- **Live** (5.14, ADR-0042) : une fois la table ouverte, football-data (dossier des bruts externes,
  ADR-0024) est superposé **en mémoire** à la saison du jour : résultats depuis le gel, dates réelles,
  cotes avant clôture des matchs à venir, fraîcheur par championnat. `staging` n'est pas modifiée ; la
  superposition ne touche que la saison courante, le rejeu (jusqu'en 2024-25) n'en voit rien.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from sqlalchemy import select, text

from foot_predictor.inference.availability import Freshness
from foot_predictor.inference.predict import InferenceContext

DATASET_VERSION = "ds-2026-09-30-ba2b91f7"
LIVE_RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
"""Dossier des bruts externes du live (football-data, ADR-0024) : celui du worktree."""


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


def api_to_internal(engine) -> dict[int, int]:
    """Identifiant API d'une équipe → identifiant interne dans `staging` (appariement du live)."""
    from sqlalchemy.orm import Session

    from foot_predictor.db.models import Team

    with Session(engine) as session:
        pairs = session.execute(select(Team.id, Team.api_team_id)).all()
    return {api: internal for internal, api in pairs if api is not None}


def registry_active_version(engine) -> str | None:
    """Modèle actif désigné par `ops.model_registry` (migration 0008), sinon None (version par défaut)."""
    from sqlalchemy.exc import ProgrammingError
    from sqlalchemy.orm import Session

    from foot_predictor.inference.store import active_version

    try:
        with Session(engine) as session:
            return active_version(session)
    except ProgrammingError:  # base pas encore en 0008
        return None


def build_context(
    engine=None, with_odds: bool = True, today: dt.date | None = None, raw_dir: Path = LIVE_RAW_DIR
) -> InferenceContext:
    from foot_predictor.features.sources import load_dataset, load_matches

    if engine is None:
        from foot_predictor.db.session import get_engine

        engine = get_engine()
    from foot_predictor.inference.models import sealed_test_done

    opened = sealed_test_done()
    matches = load_matches(engine, opened_for_inference=opened)
    run_id, finished = last_load_run(engine)
    teams, competitions = names(engine)
    odds = None
    if with_odds:
        from foot_predictor.modeling.models.market import load_market_probabilities

        odds = load_market_probabilities()
    dataset, _ = load_dataset(DATASET_VERSION)

    def h2_inputs():
        """Compositions et feuilles de match des championnats à échelle ; celles des matchs scellés aussi
        quand le test scellé H2 est terminé au journal (rejeu des saisons scellées, ADR-0052)."""
        from foot_predictor.features.leagues import LADDERS
        from foot_predictor.features.sources import load_lineups, load_team_sheets
        from foot_predictor.seal import H2_SEALED_EXPERIMENT, sealed_test_finished

        ladder = matches[matches["api_league_id"].isin(list(LADDERS))]
        gate = {
            "competition_ids": sorted(int(c) for c in ladder["competition_id"].unique()),
            "opened_for_inference": sealed_test_finished(H2_SEALED_EXPERIMENT),
        }
        return load_lineups(engine, **gate), load_team_sheets(engine, **gate)

    context = InferenceContext(
        matches=matches,
        data_version=f"load_run-{run_id}",
        freshness=staging_freshness(matches, finished),
        team_names=teams,
        competition_names=competitions,
        odds=odds,
        dataset=dataset,
        today=today or dt.datetime.now(dt.UTC).date(),
        active_version=registry_active_version(engine),
        history_opened=opened,
        h2_loader=h2_inputs,
    )
    if not opened:  # avant le test scellé H1 : pas de saison courante, donc rien à superposer
        return context
    from foot_predictor.inference import live_sources

    maps = live_sources.TeamMaps.from_yaml(api_to_internal(engine))
    return live_sources.with_overlay(context, live_sources.load_overlay(context.matches, raw_dir, maps, context.today))
