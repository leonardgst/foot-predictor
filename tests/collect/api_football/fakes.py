"""Doublures de test : fausse API-FOOTBALL, sans aucun appel réseau.

- `FakeClock` : horloge et `sleep` simulés (une pause de 60 s dure 0 s réelle) ;
- `FakeSession` : remplace `requests.Session` ; chaque appel est servi par
  une fonction `handler(endpoint, params) -> FakeResponse` ou par une liste
  de réponses consommées dans l'ordre ;
- constructeurs de corps de réponse au format api-sports ;
- `load_real_fixtures()` : les 5 matchs réels de `tests/fixtures/api_football/`.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import requests
from pydantic import SecretStr
from requests.structures import CaseInsensitiveDict

from foot_predictor.collect.api_football.client import ApiFootballClient

FIXTURES_FILE = Path(__file__).resolve().parents[2] / "fixtures" / "api_football" / "payloads_fixtures.jsonl"
TEST_KEY = "cle-de-test-ne-doit-jamais-sortir"
BASE_URL = "https://api.test"


def load_real_fixtures() -> list[dict]:
    with open(FIXTURES_FILE, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class FakeClock:
    def __init__(self) -> None:
        self.monotonic = 1000.0
        self.sleeps: list[float] = []
        self.utc = dt.datetime(2026, 10, 2, 8, 0, 0, tzinfo=dt.timezone.utc)

    def clock(self) -> float:
        return self.monotonic

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.monotonic += seconds

    def now(self) -> dt.datetime:
        # Chaque lecture avance d'une milliseconde : noms de fichiers distincts.
        self.utc += dt.timedelta(milliseconds=1)
        return self.utc


class FakeResponse:
    def __init__(self, status_code: int = 200, body: object = None, headers: dict | None = None, text: str | None = None):
        self.status_code = status_code
        self._body = body
        self._text = text
        self.headers = CaseInsensitiveDict(headers or {})

    def json(self):
        if self._text is not None:
            raise ValueError("JSON illisible")
        return copy.deepcopy(self._body)


class FakeSession:
    def __init__(self, handler=None, responses=None, remaining_day: int | None = 7000):
        self._handler = handler
        self._responses = list(responses or [])
        self.remaining_day = remaining_day
        self.calls: list[tuple[str, dict]] = []
        self.sent_headers: list[dict] = []

    def get(self, url, headers=None, params=None, timeout=None):
        endpoint = url.removeprefix(BASE_URL)
        self.calls.append((endpoint, dict(params or {})))
        self.sent_headers.append(dict(headers or {}))
        if self._responses:
            item = self._responses.pop(0)
        else:
            item = self._handler(endpoint, dict(params or {}))
        if isinstance(item, Exception):
            raise item
        if self.remaining_day is not None and item.status_code == 200:
            self.remaining_day -= 1
            item.headers.setdefault("x-ratelimit-requests-remaining", str(self.remaining_day))
            item.headers.setdefault("X-RateLimit-Remaining", "299")
        return item


def api_body(response, *, errors=None, results=None, parameters=None, paging=None) -> dict:
    if results is None:
        results = len(response) if isinstance(response, list) else 1
    return {
        "get": "test",
        "parameters": parameters or {},
        "errors": errors if errors is not None else [],
        "results": results,
        "paging": paging or {"current": 1, "total": 1},
        "response": response,
    }


def ok(response, **kwargs) -> FakeResponse:
    return FakeResponse(200, api_body(response, **kwargs))


def status_body(current: int = 100, limit_day: int = 7500) -> dict:
    return {
        "get": "status",
        "parameters": [],
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": {
            "account": {"firstname": "Test", "email": "test@example.org"},
            "subscription": {"plan": "Pro", "end": "2026-10-22T07:56:53+00:00", "active": True},
            "requests": {"current": current, "limit_day": limit_day},
        },
    }


def fixture_item(fixture_id: int, *, status: str = "FT", league: int = 39, season: int = 2015,
                 home: int = 33, away: int = 47) -> dict:
    """Élément de `/fixtures?league=&season=` réduit aux champs utiles."""
    return {
        "fixture": {"id": fixture_id, "date": "2015-08-08T14:00:00+00:00", "status": {"short": status}},
        "league": {"id": league, "season": season},
        "teams": {"home": {"id": home}, "away": {"id": away}},
    }


def make_client(session: FakeSession, clock: FakeClock, **kwargs) -> ApiFootballClient:
    kwargs.setdefault("reserve", 500)
    return ApiFootballClient(
        SecretStr(TEST_KEY),
        session=session,  # type: ignore[arg-type]
        base_url=BASE_URL,
        sleep=clock.sleep,
        clock=clock.clock,
        now=clock.now,
        **kwargs,
    )


def timeout_error() -> Exception:
    return requests.Timeout("délai dépassé simulé")
