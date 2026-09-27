"""Client HTTP : cadence, 429, 5xx, errors, réserve de quota (ADR-0004)."""
from __future__ import annotations

import pytest
from pydantic import SecretStr

from foot_predictor.collect.api_football import client as client_mod
from foot_predictor.collect.api_football.client import ApiFootballClient

from .fakes import TEST_KEY, FakeClock, FakeResponse, FakeSession, make_client, ok, status_body, timeout_error


@pytest.fixture
def clock():
    return FakeClock()


def test_sends_key_header_and_reads_quota_headers(clock):
    session = FakeSession(responses=[ok([1, 2])], remaining_day=6000)
    client = make_client(session, clock)

    response = client.get("/teams", {"league": 39, "season": 2015})

    assert session.calls == [("/teams", {"league": 39, "season": 2015})]
    assert session.sent_headers[0]["x-apisports-key"] == TEST_KEY
    assert response.results == 2 and response.errors == []
    assert response.headers_quota["x-ratelimit-requests-remaining"] == "5999"
    assert client.remaining_day == 5999
    assert client.remaining_minute == 299


def test_at_most_two_requests_per_second(clock):
    session = FakeSession(handler=lambda e, p: ok([]))
    client = make_client(session, clock)

    for _ in range(3):
        client.get("/teams", {})

    assert clock.sleeps == [pytest.approx(0.5), pytest.approx(0.5)]


def test_http_429_pauses_60_seconds_then_retries(clock):
    session = FakeSession(responses=[FakeResponse(429, {}), ok([1])])
    client = make_client(session, clock)

    response = client.get("/teams", {})

    assert response.results == 1
    assert 60 in clock.sleeps
    assert len(session.calls) == 2


def test_errors_ratelimit_is_treated_like_429(clock):
    session = FakeSession(responses=[ok([], errors={"rateLimit": "Too many requests"}), ok([1])])
    client = make_client(session, clock)

    assert client.get("/teams", {}).results == 1
    assert 60 in clock.sleeps


def test_5xx_retries_with_growing_wait_then_succeeds(clock):
    session = FakeSession(responses=[FakeResponse(503, {}), FakeResponse(502, {}), ok([1])])
    client = make_client(session, clock)

    assert client.get("/teams", {}).results == 1
    backoffs = [s for s in clock.sleeps if s >= 1]
    assert backoffs == [2, 4]


def test_5xx_or_timeout_three_times_raises_transient_error(clock):
    session = FakeSession(responses=[FakeResponse(500, {}), timeout_error(), FakeResponse(504, {})])
    client = make_client(session, clock)

    with pytest.raises(client_mod.TransientError):
        client.get("/teams", {})
    assert len(session.calls) == 3


def test_unreadable_json_is_transient(clock):
    session = FakeSession(responses=[FakeResponse(200, text="<html>"), ok([1])])
    client = make_client(session, clock)
    assert client.get("/teams", {}).results == 1


def test_other_errors_are_returned_for_the_caller(clock):
    session = FakeSession(responses=[ok([], errors={"plan": "Free plans do not have access"}, results=0)])
    client = make_client(session, clock)

    response = client.get("/fixtures", {"league": 39, "season": 2010})

    assert response.errors == {"plan": "Free plans do not have access"}
    assert len(session.calls) == 1  # aucune nouvelle tentative


def test_daily_quota_error_stops(clock):
    session = FakeSession(responses=[ok([], errors={"requests": "You have reached the request limit for the day"})])
    client = make_client(session, clock)

    with pytest.raises(client_mod.DailyQuotaExhausted):
        client.get("/teams", {})


def test_token_error_stops_without_leaking_key(clock):
    session = FakeSession(responses=[ok([], errors={"token": "Error/Missing application key"})])
    client = make_client(session, clock)

    with pytest.raises(client_mod.AuthenticationError) as excinfo:
        client.get("/teams", {})
    assert TEST_KEY not in str(excinfo.value)


def test_http_4xx_raises_http_error(clock):
    session = FakeSession(responses=[FakeResponse(404, {"message": "not found"})])
    client = make_client(session, clock)
    with pytest.raises(client_mod.HttpError):
        client.get("/inconnu", {})


def test_stops_under_reserve_before_sending(clock):
    session = FakeSession(handler=lambda e, p: ok([1]), remaining_day=503)
    client = make_client(session, clock, reserve=500)

    client.get("/teams", {})  # quota restant après : 502
    client.get("/teams", {})  # 501
    client.get("/teams", {})  # 500 : on atteint la réserve
    with pytest.raises(client_mod.QuotaReserveReached):
        client.get("/teams", {})
    assert len(session.calls) == 3


def test_status_sets_remaining_from_body(clock):
    session = FakeSession(responses=[FakeResponse(200, status_body(current=7100, limit_day=7500))], remaining_day=None)
    client = make_client(session, clock, reserve=500)

    client.status()

    assert client.remaining_day == 400
    with pytest.raises(client_mod.QuotaReserveReached):
        client.get("/teams", {})


def test_max_requests_counts_every_http_call(clock):
    session = FakeSession(responses=[FakeResponse(503, {}), ok([1]), ok([1])])
    client = make_client(session, clock, max_requests=2)

    client.get("/teams", {})  # 2 appels HTTP (503 puis succès)
    with pytest.raises(client_mod.RequestBudgetExhausted):
        client.get("/teams", {})
    assert client.requests_made == 2


def test_key_must_be_secret():
    with pytest.raises(TypeError):
        ApiFootballClient("cle-en-clair")  # type: ignore[arg-type]
    assert ApiFootballClient(SecretStr("x")).requests_made == 0
