"""API (TestClient) : contrat du rapport F.6, erreurs explicites, scellé, idempotence. Contexte synthétique."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from foot_predictor.api import app as api_module
from foot_predictor.api.__main__ import build_parser
from foot_predictor.api.app import ContextProvider, create_app
from foot_predictor.db.models import Prediction
from tests.features.test_dataset_h2 import synthetic_compositions
from tests.inference.test_h2 import h2_context
from tests.inference.test_predict import FakeModel, context, shifted_matches


@pytest.fixture(scope="module")
def ctx():
    matches = shifted_matches()
    from foot_predictor.inference.models import LoadedModel

    loaded = LoadedModel("essai-api", FakeModel(), {"version": "essai-api", "horizon": "H1",
                                                     "experiment_file": "experiments/x.yaml"}, None)  # fmt: skip
    return context(matches, loaded, today=dt.date(2023, 9, 1))


@pytest.fixture
def client(ctx, tmp_path):
    ctx.sealed_log = tmp_path / "journal.md"
    return TestClient(create_app(ContextProvider(lambda: ctx, lambda: "v-test")))


def a_match(ctx, *, played=True, league=39, season=2023):
    m = ctx.matches
    rows = m[(m["api_league_id"] == league) & (m["season_year"] == season)]
    rows = rows[rows["status"] == "played"] if played else rows[rows["status"] != "played"]
    return rows.iloc[-1]


def test_competitions_say_which_are_in_the_model_scope(client):
    body = client.get("/competitions").json()
    scope = {c["api_league_id"]: c["in_model_scope"] for c in body}
    assert scope[39] is True and scope[40] is False


def test_matches_of_a_date_with_their_availability_summary(client, ctx):
    match = a_match(ctx)
    response = client.get("/matches", params={"date": match["match_day"].isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert {m["match_id"] for m in body} >= {int(match["match_id"])}
    assert all("variables" not in m and "prediction" not in m for m in body)  # résumé seulement


def test_sealed_or_closed_dates_are_refused_with_403(client):
    for date in ("2025-08-16", "2020-10-03"):
        response = client.get("/matches", params={"date": date})
        assert response.status_code == 403 and response.json()["detail"]
    assert client.get("/matches", params={"date": "2023-01-01", "mode": "autre"}).status_code == 422


def test_after_the_opening_a_played_sealed_match_is_never_served(tmp_path):
    """ADR-0045 : table ouverte à l'inférence ; un match scellé joué répond 403 en rejeu comme en live, jamais 200."""
    from foot_predictor.inference.models import LoadedModel
    from foot_predictor.seal import H1_SEALED_EXPERIMENT, SEALED_DONE

    matches = shifted_matches(years=6)  # 2025-26 et 2026-27
    log = tmp_path / "journal.md"
    log.write_text(f"| x | y | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport z |\n", encoding="utf-8")
    upcoming = matches[matches["status"] != "played"].iloc[0]
    loaded = LoadedModel("essai-api", FakeModel(), {"version": "essai-api", "horizon": "H1"}, None)
    opened = context(matches, loaded, today=upcoming["match_day"], sealed_log=log, history_opened=True)
    api = TestClient(create_app(ContextProvider(lambda: opened, lambda: "v-test")))
    played = matches[(matches["status"] == "played") & (matches["match_day"] < upcoming["match_day"])].iloc[-1]
    for mode in ("replay", "live"):
        response = api.get(f"/matches/{int(played['match_id'])}/availability", params={"mode": mode})
        assert response.status_code == 403, mode
    listed = api.get("/matches", params={"date": played["match_day"].isoformat(), "mode": "replay"})
    assert listed.status_code == 403
    live = api.get(f"/matches/{int(upcoming['match_id'])}/availability", params={"mode": "live"})
    assert live.status_code == 200 and live.json()["status"] == "available"  # un match à venir est servi


def test_the_context_is_rebuilt_only_when_its_key_changes(ctx):
    """5.14 : la clé (chargement, fichiers de football-data, jour) est comparée à celle du dernier contexte,
    pas à sa version des données, qui peut être différente (`load_run-n+fd-…`)."""
    builds, key = [], {"value": "load_run-7+fd-a@2026-10-22"}
    provider = ContextProvider(lambda: builds.append(1) or ctx, lambda: key["value"])
    provider.get(), provider.get()
    assert len(builds) == 1  # ctx.data_version (« v-test ») diffère de la clé : aucune reconstruction pour autant
    key["value"] = "load_run-7+fd-b@2026-10-22"  # nouveau fichier téléchargé
    provider.get()
    key["value"] = "load_run-7+fd-b@2026-10-23"  # nouveau jour
    provider.get()
    assert len(builds) == 3


def test_availability_detail_and_unknown_match(client, ctx):
    match = a_match(ctx)
    body = client.get(f"/matches/{int(match['match_id'])}/availability").json()
    assert body["status"] == "available" and body["variables"]
    assert client.get("/matches/987654321/availability").status_code == 404


def test_prediction_of_an_unavailable_match_is_a_409_with_reasons(client, ctx):
    first_day = ctx.matches.loc[ctx.matches["api_league_id"] == 39, "match_day"].min()
    match = ctx.matches[(ctx.matches["match_day"] == first_day) & (ctx.matches["api_league_id"] == 39)].iloc[0]
    response = client.post(f"/matches/{int(match['match_id'])}/predictions")
    assert response.status_code == 409 and any("730 jours" in r for r in response.json()["reasons"])
    second_division = a_match(ctx, league=40)
    response = client.post(f"/matches/{int(second_division['match_id'])}/predictions")
    assert response.status_code == 409 and "hors périmètre" in response.json()["reasons"][0]


@pytest.fixture(scope="module")
def ctx_h2():
    matches = shifted_matches()
    lineups, sheets = synthetic_compositions(matches)
    return h2_context(matches, lineups, sheets, today=dt.date(2023, 9, 1))


@pytest.fixture
def client_h2(ctx_h2, tmp_path):
    ctx_h2.sealed_log = tmp_path / "journal.md"
    return TestClient(create_app(ContextProvider(lambda: ctx_h2, lambda: "v-test")))


def test_h2_replay_is_served_side_by_side_with_h1(client_h2, ctx_h2):
    match = a_match(ctx_h2)
    mid = int(match["match_id"])
    h2 = client_h2.get(f"/matches/{mid}/availability", params={"horizon": "H2"})
    assert h2.status_code == 200 and h2.json()["horizon"] == "H2" and h2.json()["model_version"] == "essai-h2"
    assert "xi_quality" in {v["variable"] for v in h2.json()["variables"]}
    h1 = client_h2.get(f"/matches/{mid}/availability").json()
    assert h1["horizon"] == "H1" and "xi_quality" not in {v["variable"] for v in h1["variables"]}
    listed = client_h2.get("/matches", params={"date": match["match_day"].isoformat(), "horizon": "H2"})
    assert listed.status_code == 200 and {m["horizon"] for m in listed.json()} == {"H2"}
    assert mid in {m["match_id"] for m in listed.json()}


def test_h2_in_live_is_a_200_with_its_reason_and_a_prediction_is_a_409(tmp_path):
    from foot_predictor.inference.availability import H2_LIVE_REASON
    from foot_predictor.inference.models import LoadedModel
    from foot_predictor.seal import H1_SEALED_EXPERIMENT, SEALED_DONE

    matches = shifted_matches(years=6)
    log = tmp_path / "journal.md"
    log.write_text(f"| x | y | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport z |\n", encoding="utf-8")
    upcoming = matches[matches["status"] != "played"].iloc[0]
    loaded = LoadedModel("essai-api", FakeModel(), {"version": "essai-api", "horizon": "H1"}, None)
    opened = context(matches, loaded, today=upcoming["match_day"], sealed_log=log, history_opened=True)
    api = TestClient(create_app(ContextProvider(lambda: opened, lambda: "v-test")))
    mid = int(upcoming["match_id"])
    answer = api.get(f"/matches/{mid}/availability", params={"horizon": "H2", "mode": "live"})
    assert answer.status_code == 200
    body = answer.json()
    assert body["status"] == "h2_unavailable" and body["reasons"] == [H2_LIVE_REASON]
    assert body["model_version"] is None and body["variables"] == []
    listed = api.get("/matches", params={"date": upcoming["match_day"].isoformat(), "mode": "live", "horizon": "H2"})
    assert listed.status_code == 200 and {m["status"] for m in listed.json()} == {"h2_unavailable"}
    refused = api.post(f"/matches/{mid}/predictions", params={"horizon": "H2", "mode": "live"})
    assert refused.status_code == 409 and refused.json()["reasons"] == [H2_LIVE_REASON]


def test_h2_without_a_composition_source_is_a_503_not_a_crash(client, ctx):
    match = a_match(ctx)  # contexte H1 : aucune lecture des compositions, ni modèle H2
    ctx._models[("replay", 2022, "H2")] = ctx._models[("replay", 2023, "H2")] = ctx._models[("replay", 2023, "H1")]
    response = client.get(f"/matches/{int(match['match_id'])}/availability", params={"horizon": "H2"})
    assert response.status_code == 503 and "compositions" in response.json()["detail"]


def test_h2_replay_dates_stay_closed_on_the_sealed_seasons(client_h2):
    response = client_h2.get("/matches", params={"date": "2025-08-16", "horizon": "H2"})
    assert response.status_code == 403


def test_the_h2_contribution_comes_from_the_experiment_reports(client):
    response = client.get("/models/h2/contribution")
    assert response.status_code == 200
    body = response.json()
    assert [s["group"] for s in body["steps"]] == ["G6", "G5", "G4"]
    assert [s["retained"] for s in body["steps"]] == [False, True, False]  # chemin de décision de 6.7 (ADR-0048)
    assert body["dataset"] == "ds-2026-11-01-e0defb32" and body["structures"] and body["g5_by_round"]
    assert "/models/h2/contribution" in client.get("/openapi.json").json()["paths"]


def test_the_h2_contribution_is_a_503_when_a_report_is_missing(client, monkeypatch):
    from foot_predictor.inference import h2_contribution

    def missing():
        raise h2_contribution.ContributionUnavailable("Rapport d'expérience absent : essai.")

    monkeypatch.setattr(h2_contribution, "load_contribution", missing)
    response = client.get("/models/h2/contribution")
    assert response.status_code == 503 and "absent" in response.json()["detail"]


def test_active_model_card_has_no_file_path_and_missing_model_is_503(client, monkeypatch):
    from foot_predictor.inference import models

    loaded = models.LoadedModel("m", None, {"version": "m", "experiment_file": "experiments/x.yaml"}, None)
    monkeypatch.setattr(api_module.model_store, "load_active", lambda version=None: loaded)
    body = client.get("/models/active").json()
    assert body["version"] == "m" and "experiment_file" not in body

    def missing(version=None):
        raise models.ModelUnavailable("Modèle absent : m")

    monkeypatch.setattr(api_module.model_store, "load_active", missing)
    assert client.get("/models/active").status_code == 503
    assert client.get("/health").json()["status"] == "degraded"


def test_freshness_lists_the_sources(client):
    body = client.get("/data/freshness").json()
    assert body["data_version"] == "v-test" and len(body["sources"]) == 2


def test_freshness_lists_each_top5_league_of_the_live(ctx):
    import dataclasses

    from foot_predictor.inference.availability import Freshness

    fresh = {39: Freshness("football-data (live)", dt.date(2026, 10, 22), dt.datetime(2026, 10, 22, 14, tzinfo=dt.UTC)),
             40: Freshness("football-data (live)", dt.date(2026, 10, 21), None)}  # fmt: skip
    live = dataclasses.replace(ctx, league_freshness=fresh)
    body = TestClient(create_app(ContextProvider(lambda: live, lambda: "v"))).get("/data/freshness").json()
    leagues = [s for s in body["sources"] if s["source"].startswith("football-data (live)")]
    assert len(leagues) == 1 and leagues[0]["complete_until"] == "2026-10-22"  # top 5 seulement (40 : D2)


def test_openapi_documentation_is_generated(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/competitions", "/matches", "/matches/{match_id}/availability",
            "/matches/{match_id}/predictions", "/models/active", "/models/h2/contribution",
            "/data/freshness"} <= set(paths)  # fmt: skip


def test_serve_refuses_a_non_local_address():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["serve", "--host", "0.0.0.0"])
    assert build_parser().parse_args(["serve"]).host == "127.0.0.1"


@pytest.mark.db
def test_creating_a_prediction_is_traced_and_idempotent(ctx, tmp_path, _test_engine):
    ctx.sealed_log = tmp_path / "journal.md"
    app = create_app(ContextProvider(lambda: ctx, lambda: "v-test"), sessions=lambda: Session(_test_engine))
    client = TestClient(app)
    match = a_match(ctx)
    url = f"/matches/{int(match['match_id'])}/predictions"
    try:
        first = client.post(url)
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["saved"]["created"] is True and body["prediction"]["interval"]["announced_coverage"] > 0
        assert body["actual_score"] is not None
        with Session(_test_engine) as session:  # E-058 : la route trace l'identifiant API du match
            traced = session.get(Prediction, body["saved"]["id"])
            assert traced.api_fixture_id == int(match["api_fixture_id"])
        again = client.post(url)
        assert again.status_code == 200 and again.json()["saved"]["id"] == body["saved"]["id"]
        forced = client.post(url, params={"force": "true"})
        assert forced.status_code == 201 and forced.json()["saved"]["id"] != body["saved"]["id"]
    finally:
        with Session(_test_engine) as session:
            session.execute(delete(Prediction).where(Prediction.model_version == "essai-api"))
            session.commit()
