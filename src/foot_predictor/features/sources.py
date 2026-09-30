"""Porte unique de lecture des matchs (scellé technique, ADR-0012 et ADR du scellé technique).

**Toute** lecture des matchs pour les variables, les notebooks et, plus tard, `modeling/`
passe par ce module. Il lit `staging` et filtre les matchs sous scellés **à la source**,
dans la requête SQL (`match_date < SEAL_DATE`), jamais après coup. `check_seal` vérifie
ensuite le résultat (seconde barrière).

Un test d'architecture (`tests/features/test_architecture.py`) vérifie qu'aucun autre module
de `features/` n'importe le modèle `Match` ni n'écrit de SQL sur `staging.match`, et que les
notebooks n'importent que ce module.

Règles de date (registre des variables) : la date d'un match est la date UTC de son coup
d'envoi (`match_date`, égal à `kickoff_utc` pour un match API) ; pour un match « hors API »,
c'est la date de football-data, stockée à minuit UTC.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, bindparam, text
from sqlalchemy.orm import Session

from foot_predictor.seal import SEAL_TIMESTAMP, check_seal

# Une ligne par match ; les colonnes « home_* » et « away_* » viennent des deux lignes de
# staging.team_match, de leurs statistiques API (staging.team_match_stats) et de leurs tirs
# football-data (staging.team_match_stats_external, migration 0005).
_MATCH_SQL = """
select
    m.id                     as match_id,
    m.api_fixture_id         as api_fixture_id,
    m.match_date             as match_date,
    m.competition_id         as competition_id,
    c.api_league_id          as api_league_id,
    c.name                   as competition_name,
    c.country                as country,
    c.kind                   as competition_kind,
    m.season_id              as season_id,
    s.year                   as season_year,
    m.round                  as round,
    m.home_team_id           as home_team_id,
    m.away_team_id           as away_team_id,
    m.home_goals_90          as home_goals_90,
    m.away_goals_90          as away_goals_90,
    m.status::text           as status,
    m.excluded               as excluded,
    m.exclusion_reason       as exclusion_reason,
    m.origin                 as origin,
    hs.shots_total           as home_shots_api,
    hs.shots_on_goal         as home_sot_api,
    hs.expected_goals        as home_xg_api,
    aws.shots_total          as away_shots_api,
    aws.shots_on_goal        as away_sot_api,
    aws.expected_goals       as away_xg_api,
    hfd.shots                as home_shots_fd,
    hfd.shots_on_target      as home_sot_fd,
    afd.shots                as away_shots_fd,
    afd.shots_on_target      as away_sot_fd
from staging.match m
join staging.competition c on c.id = m.competition_id
join staging.season s on s.id = m.season_id
left join staging.team_match htm on htm.match_id = m.id and htm.is_home
left join staging.team_match_stats hs on hs.team_match_id = htm.id
left join staging.team_match atm on atm.match_id = m.id and not atm.is_home
left join staging.team_match_stats aws on aws.team_match_id = atm.id
left join staging.team_match_stats_external hfd on hfd.team_match_id = htm.id and hfd.source = 'football_data'
left join staging.team_match_stats_external afd on afd.team_match_id = atm.id and afd.source = 'football_data'
where m.match_date < :upper
{extra}
order by m.match_date, m.id
"""

_INT_COLUMNS = [
    "match_id",
    "api_fixture_id",
    "competition_id",
    "api_league_id",
    "season_id",
    "season_year",
    "home_team_id",
    "away_team_id",
    "home_goals_90",
    "away_goals_90",
    "home_shots_api",
    "home_sot_api",
    "away_shots_api",
    "away_sot_api",
    "home_shots_fd",
    "home_sot_fd",
    "away_shots_fd",
    "away_sot_fd",
]
_FLOAT_COLUMNS = ["home_xg_api", "away_xg_api"]


def _upper_bound(until: dt.date | None, sealed_test: bool) -> pd.Timestamp:
    """Borne supérieure stricte des dates lues : le scellé, ou `until` s'il est plus tôt."""
    if until is not None:
        until_ts = pd.Timestamp(until, tz="UTC")
        return until_ts if sealed_test else min(until_ts, SEAL_TIMESTAMP)
    return pd.Timestamp("2200-01-01", tz="UTC") if sealed_test else SEAL_TIMESTAMP


def load_matches(
    connectable=None,
    *,
    competition_ids: Iterable[int] | None = None,
    kinds: Iterable[str] | None = None,
    until: dt.date | None = None,
    sealed_test: bool = False,
    experiment: str | None = None,
    sealed_log: Path | None = None,
) -> pd.DataFrame:
    """Matchs de `staging`, une ligne par match, antérieurs au scellé.

    Paramètres :
    - `connectable` : moteur, connexion ou session SQLAlchemy (par défaut, la base de `APP_ENV`) ;
    - `competition_ids`, `kinds` (`league`, `cup`) : filtres facultatifs, appliqués en SQL ;
    - `until` : borne stricte supplémentaire (matchs datés **avant** ce jour), pour rejouer
      l'historique connu à une date donnée (contrôle d'invariance à la date de coupe) ;
    - `sealed_test=True` : lève le filtre du scellé, exige `experiment` et journalise l'usage
      (`reports/sealed_tests.md`). Réservé au test scellé, une fois par version (ADR-0012).

    Colonnes : identifiants (match, fixture API, compétition, saison, équipes), `match_date`
    (UTC), `match_day` (date UTC), `country`, `competition_kind`, `season_year`, `round`,
    `is_regular_season`, buts au temps réglementaire, `status`, `excluded`,
    `exclusion_reason`, `origin`, tirs, tirs cadrés et xG d'API-FOOTBALL par équipe
    (`*_api`), tirs et tirs cadrés de football-data par équipe (`*_fd`, ADR-0029).
    Aucune valeur n'est remplie : une donnée absente reste vide (`<NA>`).
    """
    if connectable is None:
        from foot_predictor.db.session import get_engine

        connectable = get_engine()
    if isinstance(connectable, Session):
        connectable = connectable.connection()  # session -> sa connexion (même transaction)
    if isinstance(connectable, Engine):
        with connectable.connect() as connection:
            return load_matches(
                connection,
                competition_ids=competition_ids,
                kinds=kinds,
                until=until,
                sealed_test=sealed_test,
                experiment=experiment,
                sealed_log=sealed_log,
            )

    extra, params = [], {"upper": _upper_bound(until, sealed_test).to_pydatetime()}
    binds = []
    if competition_ids is not None:
        extra.append("and m.competition_id in :competition_ids")
        params["competition_ids"] = [int(c) for c in competition_ids]
        binds.append(bindparam("competition_ids", expanding=True))
    if kinds is not None:
        extra.append("and c.kind in :kinds")
        params["kinds"] = list(kinds)
        binds.append(bindparam("kinds", expanding=True))
    query = text(_MATCH_SQL.format(extra="\n".join(extra)))
    if binds:
        query = query.bindparams(*binds)

    # Sans parallélisme : dans le conteneur Docker, /dev/shm (64 Mo) ne suffit pas aux jointures
    # parallèles sur toute la table des matchs (« could not resize shared memory segment », E-035).
    connectable.execute(text("set max_parallel_workers_per_gather = 0"))
    frame = pd.read_sql(query, connectable, params=params)
    frame["match_date"] = pd.to_datetime(frame["match_date"], utc=True)
    check_seal(frame["match_date"], sealed_test=sealed_test, experiment=experiment, log_path=sealed_log)

    for column in _INT_COLUMNS:
        frame[column] = frame[column].astype("Int64")
    for column in _FLOAT_COLUMNS:
        frame[column] = pd.to_numeric(frame[column]).astype("Float64")
    frame["match_day"] = frame["match_date"].dt.tz_convert("UTC").dt.date
    frame["is_regular_season"] = (frame["competition_kind"] == "league") & (
        frame["round"].isna() | frame["round"].fillna("").str.startswith("Regular Season")
    )
    return frame


def list_datasets(root: Path | None = None) -> list[str]:
    """Versions de jeux de données présentes (dossiers `ds-*` avec un manifeste), de la plus ancienne à la plus récente.

    Ordre : date du manifeste, puis date d'écriture du manifeste. Le nom seul ne suffit pas : deux
    versions du même jour se départagent par leur sha256, qui n'a rien de chronologique.
    """
    import json

    from foot_predictor.features.dataset import DATASETS_ROOT

    base = Path(root) if root else DATASETS_ROOT
    if not base.exists():
        return []
    found = []
    for folder in base.glob("ds-*"):
        manifest = folder / "manifest.json"
        if manifest.exists():
            date = json.loads(manifest.read_text(encoding="utf-8")).get("date", "")
            found.append((date, manifest.stat().st_mtime, folder.name))
    return [name for _, _, name in sorted(found)]


def load_dataset(version: str | None = None, root: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Lit un jeu de données versionné (la plus récente version par défaut) et son manifeste.

    Seconde barrière du scellé : un jeu qui contiendrait un match à partir du 1er juillet 2025
    est refusé (`check_seal`). Les notebooks lisent les données par cette fonction ou par
    `load_matches`, jamais directement.
    """
    import json

    from foot_predictor.features.dataset import DATA_FILE, DATASETS_ROOT

    base = Path(root) if root else DATASETS_ROOT
    versions = list_datasets(base)
    if not versions:
        raise FileNotFoundError(f"Aucun jeu de données dans {base} : lancer python -m foot_predictor.features build")
    version = version or versions[-1]
    folder = base / version
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(folder / DATA_FILE)
    check_seal(frame["match_date"])
    return frame, manifest


# Cotes plus/moins 2,5 (ADR-0036) : une ligne par (match, version), mêmes filtres du scellé que les matchs.
_ODDS_SQL = """
select
    o.match_id               as match_id,
    m.match_date             as match_date,
    o.version                as version,
    o.odds_over_2_5          as odds_over_2_5,
    o.odds_under_2_5         as odds_under_2_5,
    o.odds_column            as odds_column,
    o.n_odds                 as n_odds
from staging.match_odds o
join staging.match m on m.id = o.match_id
where m.match_date < :upper and o.source = 'football_data'
order by o.match_id, o.version
"""


def load_odds(connectable=None, *, until: dt.date | None = None) -> pd.DataFrame:
    """Cotes plus/moins 2,5 de football-data des matchs antérieurs au scellé (référence de marché, ADR-0036).

    Même porte que `load_matches` : filtre du scellé dans la requête SQL, puis `check_seal`.
    Pas d'option `sealed_test` ici : le test scellé (4.16) lira les cotes par sa propre commande,
    journalisée. Colonnes : `match_id`, `match_date`, `version` (`avant_cloture`, `cloture`),
    `odds_over_2_5`, `odds_under_2_5`, `odds_column`, `n_odds`.
    """
    if connectable is None:
        from foot_predictor.db.session import get_engine

        connectable = get_engine()
    if isinstance(connectable, Session):
        connectable = connectable.connection()
    if isinstance(connectable, Engine):
        with connectable.connect() as connection:
            return load_odds(connection, until=until)
    params = {"upper": _upper_bound(until, sealed_test=False).to_pydatetime()}
    connectable.execute(text("set max_parallel_workers_per_gather = 0"))  # /dev/shm du conteneur (E-035)
    frame = pd.read_sql(text(_ODDS_SQL), connectable, params=params)
    frame["match_date"] = pd.to_datetime(frame["match_date"], utc=True)
    check_seal(frame["match_date"])
    frame["match_id"] = frame["match_id"].astype("int64")
    for column in ("odds_over_2_5", "odds_under_2_5"):
        frame[column] = frame[column].astype(float)
    frame["n_odds"] = frame["n_odds"].astype("Int64")
    return frame
