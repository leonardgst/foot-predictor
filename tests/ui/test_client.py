"""Client HTTP de l'interface : routes appelées, erreurs de l'API traduites, API injoignable."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from foot_predictor.ui import client as client_module
from foot_predictor.ui.client import ApiClient, ApiProblem
from tests.ui.fake_api import DAY, FakeApi


@pytest.fixture
def api():
    return FakeApi()


def test_matches_sends_date_and_mode(api):
    client = ApiClient("http://api.test", transport=api.transport())
    body = client.matches(dt.date.fromisoformat(DAY), "replay")
    assert len(body) == 3
    method, path, params = api.calls[-1]
    assert (method, path) == ("GET", "/matches") and params == {"date": DAY, "mode": "replay"}


def test_competitions_are_repeated_query_parameters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["competition"] = request.url.params.get_list("competition")
        seen["mode"] = request.url.params["mode"]
        return httpx.Response(200, json=[])

    ApiClient("http://api.test", transport=httpx.MockTransport(handler)).matches(dt.date(2024, 3, 9), "live", [1, 2])
    assert seen == {"competition": ["1", "2"], "mode": "live"}


def test_errors_of_the_api_become_readable_problems(api):
    client = ApiClient("http://api.test", transport=api.transport())
    with pytest.raises(ApiProblem) as sealed:
        client.matches(dt.date(2025, 8, 16), "replay")
    assert sealed.value.status == 403 and "scellés" in sealed.value.detail
    with pytest.raises(ApiProblem) as unavailable:
        client.predict(2, "replay")
    assert unavailable.value.status == 409 and "730 jours" in unavailable.value.reasons[0]
    with pytest.raises(ApiProblem) as unknown:
        client.availability(99, "replay")
    assert unknown.value.status == 404


def test_validation_errors_get_a_generic_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"loc": ["query", "date"], "msg": "invalid"}]})

    with pytest.raises(ApiProblem) as problem:
        ApiClient("http://api.test", transport=httpx.MockTransport(handler)).health()
    assert problem.value.status == 422 and "HTTP 422" in problem.value.detail


def test_unreachable_api_says_how_to_start_it():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusée", request=request)

    with pytest.raises(ApiProblem) as problem:
        ApiClient("http://127.0.0.1:1", transport=httpx.MockTransport(handler)).health()
    assert problem.value.status is None and "foot_predictor.api serve" in problem.value.detail


def test_prediction_creation_is_a_post_and_idempotent_on_the_api_side(api):
    client = ApiClient("http://api.test", transport=api.transport())
    first, again = client.predict(1, "replay"), client.predict(1, "replay")
    assert api.calls[-1][0] == "POST"
    assert first["saved"]["created"] is True and again["saved"]["created"] is False


def test_api_url_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("FP_API_URL", raising=False)
    assert client_module.api_url() == "http://127.0.0.1:8000"
    monkeypatch.setenv("FP_API_URL", "http://127.0.0.1:9000/")
    assert ApiClient().base_url == "http://127.0.0.1:9000"
