"""Bout en bout en rejeu (sous-étape 5.11) : brut → `load` → porte des données → inférence → API → interface.

Une petite ligue synthétique (4 équipes, aller-retour, saisons 2022-23 et 2023-24) est écrite comme le
collecteur l'écrirait (bruts API-FOOTBALL et CSV football-data pour les tirs), chargée par le vrai
`load` dans la base de test, lue par `features/sources.py`, servie par l'API (`TestClient`) et
affichée par l'interface (`AppTest`, branchée sur le transport du `TestClient`). Un clic sur
« Prédiction » affiche la loi du total et écrit la prédiction dans `ops.prediction`.

Le modèle de rejeu de 2023-24 est appris, par la procédure du pli, sur des lignes synthétiques
réalistes (2015-16 à 2022-23) : la mini-ligue est trop petite pour les 18 coefficients de M3.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

from foot_predictor.api.app import ContextProvider, create_app
from foot_predictor.collect import raw_bytes
from foot_predictor.collect.api_football.plan import parse_config
from foot_predictor.collect.football_data.download import season_dir
from foot_predictor.features.sources import load_matches
from foot_predictor.inference.availability import AVAILABLE
from foot_predictor.inference.context import last_load_run, names, staging_freshness
from foot_predictor.inference.predict import InferenceContext
from foot_predictor.ingestion.pipeline import run_load
from foot_predictor.ui import client as ui_client
from tests.modeling.synthetic import realistic_rows
from tests.quality.test_raw_check import FLAGS, RawBuilder, listing_of, synthetic
from tests.ui.test_app import APP

SEASONS = (2022, 2023)
TEAMS = (1, 2, 3, 4)
ROUNDS = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]
CONFIG = {"tiers": {"P1": {"blocks": [
    {"name": "top5", "kind": "league", "leagues": [39], "seasons": {"first": 2022, "last": 2023},
     "endpoints": ["fixtures_list", "fixtures_detail", "players"]},
]}}}  # fmt: skip


def schedule(seed: int = 3) -> list[dict]:
    """Aller-retour à 4 équipes, une journée par semaine : chaque affiche une fois par saison."""
    rng = np.random.default_rng(seed)
    matches, fid = [], 9000
    for season in SEASONS:
        start = dt.date(season, 8, 6)
        for week in range(6):
            for a, b in ROUNDS[week % 3]:
                home, away = (TEAMS[a], TEAMS[b]) if week < 3 else (TEAMS[b], TEAMS[a])
                fid += 1
                goals = [int(g) for g in rng.integers(0, 4, 2)]
                shots = [int(s) for s in rng.integers(6, 18, 2)]
                on_target = [int(s) for s in rng.integers(1, 6, 2)]
                matches.append({"fid": fid, "season": season, "day": start + dt.timedelta(days=7 * week),
                                "home": home, "away": away, "goals": goals, "shots": shots, "sot": on_target})  # fmt: skip
    return matches


def write_sources(tmp_path, matches: list[dict]):
    raw, external = tmp_path / "raw", tmp_path / "externe"
    builder = RawBuilder(raw)
    builder.leagues({39: FLAGS}, years=SEASONS)
    for season in SEASONS:
        details = []
        for m in (m for m in matches if m["season"] == season):
            item = synthetic(m["fid"], m["day"].isoformat(), m["home"], m["away"], [m["home"] * 100 + 1],
                             [m["away"] * 100 + 1])  # fmt: skip
            item["goals"] = {"home": m["goals"][0], "away": m["goals"][1]}
            item["score"] = {"fulltime": {"home": m["goals"][0], "away": m["goals"][1]}}
            details.append(item)
        builder.fixtures_list(39, listing_of(details), tier="P1", season=season)
        builder.details(39, details, tier="P1", season=season)
        builder.profiles(39, [], tier="P1", season=season)
        lines = ["Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST"] + [
            f"E0,{m['day']:%d/%m/%Y},Club {m['home']},Club {m['away']},{m['goals'][0]},{m['goals'][1]},"
            f"{m['shots'][0]},{m['shots'][1]},{m['sot'][0]},{m['sot'][1]}"
            for m in matches if m["season"] == season
        ]  # fmt: skip
        raw_bytes.write_bytes(external, season_dir(season), "E0", ".csv", "\r\n".join(lines).encode(),
                              dt.datetime(2026, 10, 4, tzinfo=dt.UTC))  # fmt: skip
    builder.queue.close()
    return raw, external


@pytest.fixture
def loaded(_test_engine, tmp_path, monkeypatch):
    """Base de test chargée par le vrai `load` ; vidée à la fin (comme le test du pipeline)."""
    monkeypatch.setattr("foot_predictor.ingestion.yaml_mappings.football_data_teams",
                        lambda directory=None: ({f"Club {t}": t for t in TEAMS}, set(), {}))  # fmt: skip
    monkeypatch.setattr("foot_predictor.ingestion.yaml_mappings.division_to_league", lambda directory=None: {"E0": 39})
    monkeypatch.setattr("foot_predictor.ingestion.yaml_mappings.player_aliases", lambda directory=None: {})
    matches = schedule()
    raw, external = write_sources(tmp_path, matches)
    summary = run_load(_test_engine, raw, external, _test_engine.url.database, parse_config(CONFIG), tmp_path / "w")
    yield _test_engine, matches, summary
    with _test_engine.begin() as connection:
        connection.execute(text("TRUNCATE ops.prediction"))
        connection.execute(text("TRUNCATE staging.competition, staging.team, staging.player, staging.coach CASCADE"))
        connection.execute(text("TRUNCATE ops.load_run CASCADE"))


@pytest.mark.db
def test_replay_end_to_end_from_raw_files_to_the_interface(loaded, tmp_path, monkeypatch):
    engine, matches, summary = loaded
    # 1. Migration et chargement : base à la dernière révision, 24 matchs et leurs tirs de football-data.
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0008_ops_prediction"
    assert summary["fingerprints"]["match"]["rows"] == 24
    assert summary["counts"]["fd_rates"] == {"E0:2022": [12, 12], "E0:2023": [12, 12]}

    # 2. Contexte d'inférence lu par la porte des données (aucune lecture directe de staging).
    table = load_matches(engine)
    run_id, finished = last_load_run(engine)
    teams, competitions = names(engine)
    context = InferenceContext(
        matches=table, data_version=f"load_run-{run_id}", freshness=staging_freshness(table, finished),
        team_names=teams, competition_names=competitions,
        dataset=realistic_rows(seasons=range(2015, 2024), leagues=(39, 140), teams_per_league=10, rounds=10),
        today=dt.date(2026, 10, 4), sealed_log=tmp_path / "journal.md", replay_root=tmp_path / "rejeu",
    )  # fmt: skip
    api = TestClient(create_app(ContextProvider(lambda: context, lambda: context.data_version),
                                sessions=lambda: Session(engine)))  # fmt: skip

    # 3. API : la première journée n'a pas d'historique (indisponible, raisons) ; la 5e de 2023-24 est prédite.
    first_day = min(m["day"] for m in matches)
    first = api.get("/matches", params={"date": first_day.isoformat()}).json()
    assert first and all(m["status"] == "unavailable" and m["reasons"] for m in first)
    day = dt.date(2023, 9, 3)
    listed = api.get("/matches", params={"date": day.isoformat()}).json()
    assert len(listed) == 2 and all(m["status"] == AVAILABLE for m in listed), listed
    assert all(m["model_version"] == "rejeu-2023-m3_g0g2" for m in listed)
    assert api.get("/matches", params={"date": "2025-08-16"}).status_code == 403  # scellé

    # 4. Interface : elle n'appelle que l'API (transport du TestClient) ; un clic prédit et trace.
    monkeypatch.setattr(ui_client, "TRANSPORT", api._transport)
    monkeypatch.setenv("FP_API_URL", "http://testserver")
    ui = AppTest.from_file(str(APP), default_timeout=120).run()
    ui.date_input(key="date_replay").set_value(day).run()
    assert not ui.exception
    target = listed[0]["match_id"]
    assert ui.button(key=f"predict_{target}").disabled is False
    ui.button(key=f"predict_{target}").click().run()
    assert not ui.exception and ui.session_state.screen == "Détail"
    metrics = {m.label: m.value for m in ui.metric}
    assert {"E[T] (buts attendus)", "λ domicile", "λ extérieur", "P(T > 2,5)"} <= set(metrics)
    page = "\n".join([m.value for m in ui.markdown] + [i.value for i in ui.info] + [c.value for c in ui.caption])
    assert "couverture annoncée" in page and "Score réel (rejeu)" in page and "rejeu-2023-m3_g0g2" in page

    # 5. Traçabilité : une ligne de ops.prediction, mode rejeu, loi du total complète.
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT mode, status, model_version, total_distribution FROM ops.prediction WHERE match_id = :m"),
            {"m": target},
        ).mappings().all()  # fmt: skip
    assert len(rows) == 1 and rows[0]["mode"] == "replay" and rows[0]["status"] == AVAILABLE
    assert abs(sum(rows[0]["total_distribution"].values()) - 1) < 1e-9
