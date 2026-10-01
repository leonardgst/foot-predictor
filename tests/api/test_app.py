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


def test_availability_detail_unknown_match_and_h2(client, ctx):
    match = a_match(ctx)
    body = client.get(f"/matches/{int(match['match_id'])}/availability").json()
    assert body["status"] == "available" and body["variables"]
    assert client.get("/matches/987654321/availability").status_code == 404
    assert client.get(f"/matches/{int(match['match_id'])}/availability", params={"horizon": "H2"}).status_code == 501


def test_prediction_of_an_unavailable_match_is_a_409_with_reasons(client, ctx):
    first_day = ctx.matches.loc[ctx.matches["api_league_id"] == 39, "match_day"].min()
    match = ctx.matches[(ctx.matches["match_day"] == first_day) & (ctx.matches["api_league_id"] == 39)].iloc[0]
    response = client.post(f"/matches/{int(match['match_id'])}/predictions")
    assert response.status_code == 409 and any("730 jours" in r for r in response.json()["reasons"])
    second_division = a_match(ctx, league=40)
    response = client.post(f"/matches/{int(second_division['match_id'])}/predictions")
    assert response.status_code == 409 and "hors périmètre" in response.json()["reasons"][0]


def test_h2_prediction_is_not_implemented(client, ctx):
    match = a_match(ctx)
    assert client.post(f"/matches/{int(match['match_id'])}/predictions", params={"horizon": "H2"}).status_code == 501


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


def test_openapi_documentation_is_generated(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/competitions", "/matches", "/matches/{match_id}/availability",
            "/matches/{match_id}/predictions", "/models/active", "/data/freshness"} <= set(paths)  # fmt: skip


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
        again = client.post(url)
        assert again.status_code == 200 and again.json()["saved"]["id"] == body["saved"]["id"]
        forced = client.post(url, params={"force": "true"})
        assert forced.status_code == 201 and forced.json()["saved"]["id"] != body["saved"]["id"]
    finally:
        with Session(_test_engine) as session:
            session.execute(delete(Prediction).where(Prediction.model_version == "essai-api"))
            session.commit()
