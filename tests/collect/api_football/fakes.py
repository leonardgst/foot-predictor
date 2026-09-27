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
    _created = 0

    def __init__(self) -> None:
        # Chaque horloge démarre une heure après la précédente : deux
        # lancements successifs d'un même test ne produisent jamais le même
        # nom de fichier (le brut refuserait, à raison, d'écraser).
        FakeClock._created += 1
        self.monotonic = 1000.0
        self.sleeps: list[float] = []
        self.utc = dt.datetime(2026, 10, 2, 8, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(hours=FakeClock._created)

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


class FakeApi:
    """Fausse API-FOOTBALL cohérente, pour les tests de bout en bout.

    - `listings[(league, season)]` : éléments renvoyés par `/fixtures?league=&season=` ;
    - `details[id]` : élément complet renvoyé par `/fixtures?ids=` (par défaut
      les 5 matchs réels ; un id absent n'est pas renvoyé) ;
    - `teams[(league, season)]` : identifiants d'équipes de `/teams` ;
    - `player_pages[(league, season)]` : nombre de pages de `/players` ;
    - `errors[(endpoint, clé de params)]` : `errors` à renvoyer ;
    - `empty` : ensemble de (endpoint, clé de params) renvoyant results = 0.
    """

    def __init__(self) -> None:
        self.listings: dict[tuple[int, int], list[dict]] = {}
        self.details: dict[int, dict] = {f["fixture"]["id"]: f for f in load_real_fixtures()}
        self.teams: dict[tuple[int, int], list[int]] = {}
        self.player_pages: dict[tuple[int, int], int] = {}
        self.errors: dict[tuple[str, tuple], dict] = {}
        self.empty: set[tuple[str, tuple]] = set()

    @staticmethod
    def key(endpoint: str, params: dict) -> tuple[str, tuple]:
        return endpoint, tuple(sorted(params.items()))

    def __call__(self, endpoint: str, params: dict) -> FakeResponse:
        key = self.key(endpoint, params)
        if key in self.errors:
            return ok([], errors=self.errors[key], results=0)
        if key in self.empty:
            return ok([], results=0)
        if endpoint == "/status":
            return FakeResponse(200, status_body())
        if endpoint == "/fixtures" and "ids" in params:
            ids = [int(i) for i in params["ids"].split("-")]
            return ok([self.details[i] for i in ids if i in self.details])
        if endpoint == "/fixtures":
            return ok(self.listings.get((params["league"], params["season"]), []))
        if endpoint == "/teams":
            teams = self.teams.get((params["league"], params["season"]), [])
            return ok([{"team": {"id": t, "name": f"Équipe {t}"}, "venue": {}} for t in teams])
        if endpoint == "/players":
            total = self.player_pages.get((params["league"], params["season"]), 1)
            page = params.get("page", 1)
            return ok([{"player": {"id": page * 100 + i}} for i in range(2)], paging={"current": page, "total": total})
        if endpoint in ("/coachs", "/transfers", "/injuries"):
            return ok([{"team": params.get("team")}])
        if endpoint == "/leagues":
            return ok(leagues_response())
        raise AssertionError(f"Appel inattendu : {endpoint} {params}")


def league_entry(league_id: int, name: str, seasons: dict[int, dict]) -> dict:
    """Élément de `/leagues` ; `seasons` : année -> surcharges de `coverage`."""
    base = {
        "fixtures": {"events": True, "lineups": True, "statistics_fixtures": True, "statistics_players": True},
        "standings": True, "players": True, "injuries": True, "predictions": True, "odds": False,
    }
    items = []
    for year, overrides in seasons.items():
        coverage = copy.deepcopy(base)
        for path, value in overrides.items():
            target = coverage
            *parents, leaf = path.split(".")
            for part in parents:
                target = target[part]
            target[leaf] = value
        items.append({"year": year, "start": f"{year}-08-01", "end": f"{year + 1}-05-31", "current": False,
                      "coverage": coverage})
    return {"league": {"id": league_id, "name": name, "type": "League"}, "country": {"name": "England"},
            "seasons": items}


def leagues_response() -> list[dict]:
    return [
        league_entry(39, "Premier League", {2013: {"fixtures.lineups": False}, 2014: {}, 2015: {"injuries": False}}),
        league_entry(45, "FA Cup", {2015: {}}),
    ]


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
