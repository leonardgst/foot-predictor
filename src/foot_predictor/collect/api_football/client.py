"""Client HTTP API-FOOTBALL : cadence, quota, erreurs (ADR-0004, rapport G.6).

Règles appliquées à chaque requête :

| Situation | Réaction |
|---|---|
| moins de 0,5 s depuis la requête précédente | attente (au plus 2 requêtes par seconde) |
| quota du jour restant <= réserve | `QuotaReserveReached` : arrêt propre, rien n'est envoyé |
| nombre maximal de requêtes du lancement atteint | `RequestBudgetExhausted` |
| HTTP 429, ou `errors.rateLimit` (limite par minute) | pause de 60 s puis nouvelle tentative |
| HTTP 5xx, délai dépassé, connexion coupée, JSON illisible | 3 tentatives (attentes 2 s puis 4 s), puis `TransientError` |
| `errors.requests` (quota du jour épuisé) | `DailyQuotaExhausted` : arrêt propre |
| `errors.token` (clé absente ou invalide) | `AuthenticationError` : arrêt |
| autre code HTTP 4xx | `HttpError` |
| autre `errors` non vide | réponse renvoyée telle quelle : c'est l'appelant qui la stocke et marque la tâche `failed` |

Quota : l'en-tête `x-ratelimit-requests-remaining` donne le quota **du jour**
restant, `X-RateLimit-Remaining` celui de la **minute**. Les deux sont lus à
chaque réponse et conservés dans l'enveloppe.

La clé n'est utilisée que pour construire l'en-tête `x-apisports-key` : elle
n'apparaît jamais dans les messages, le journal ou les fichiers.

Horloge, pause et session HTTP sont injectables : les tests ne font ni appel
réseau, ni pause réelle.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from pydantic import SecretStr

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
DAY_REMAINING = "x-ratelimit-requests-remaining"
MINUTE_REMAINING = "X-RateLimit-Remaining"
QUOTA_HEADERS = ("x-ratelimit-requests-limit", DAY_REMAINING, "X-RateLimit-Limit", MINUTE_REMAINING)

DEFAULT_RESERVE = 500
MIN_INTERVAL_SECONDS = 0.5
RATE_LIMIT_PAUSE_SECONDS = 60
MAX_RATE_LIMIT_PAUSES = 5
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2
TIMEOUT_SECONDS = 30


class CollectStop(Exception):
    """Arrêt propre de la collecte : la tâche en cours reste `pending`."""


class QuotaReserveReached(CollectStop):
    pass


class DailyQuotaExhausted(CollectStop):
    pass


class RequestBudgetExhausted(CollectStop):
    pass


class AuthenticationError(CollectStop):
    pass


class TransientError(Exception):
    """Échec temporaire persistant après toutes les tentatives."""


class HttpError(Exception):
    """Réponse HTTP 4xx (hors 429) : la requête elle-même est en cause."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def normalize_errors(errors: object) -> dict | list:
    """L'API renvoie `[]` sans erreur, un dict (ou une liste) sinon."""
    if errors is None:
        return []
    return errors


def to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass
class ApiResponse:
    endpoint: str
    params: dict
    http_status: int
    headers_quota: dict
    body: dict
    fetched_at: dt.datetime
    duration_ms: int

    @property
    def errors(self) -> dict | list:
        return normalize_errors(self.body.get("errors"))

    @property
    def results(self) -> int | None:
        return to_int(self.body.get("results"))


class ApiFootballClient:
    def __init__(
        self,
        api_key: SecretStr,
        *,
        session: requests.Session | None = None,
        reserve: int = DEFAULT_RESERVE,
        max_requests: int | None = None,
        base_url: str = BASE_URL,
        min_interval: float = MIN_INTERVAL_SECONDS,
        timeout: float = TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], dt.datetime] = utc_now,
    ) -> None:
        if not isinstance(api_key, SecretStr):
            raise TypeError("La clé doit être un SecretStr (elle ne doit jamais apparaître en clair).")
        self._api_key = api_key
        self._session = session or requests.Session()
        self.reserve = reserve
        self.max_requests = max_requests
        self._base_url = base_url
        self._min_interval = min_interval
        self._timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._last_request_at: float | None = None
        self.requests_made = 0
        self.remaining_day: int | None = None
        self.remaining_minute: int | None = None

    def get(self, endpoint: str, params: dict) -> ApiResponse:
        transient_failures = 0
        rate_limit_pauses = 0
        while True:
            self._check_can_send()
            self._throttle()
            self.requests_made += 1
            started = self._clock()
            fetched_at = self._now()
            try:
                response = self._session.get(
                    f"{self._base_url}{endpoint}",
                    headers={"x-apisports-key": self._api_key.get_secret_value()},
                    params=params,
                    timeout=self._timeout,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                transient_failures = self._transient(
                    transient_failures, endpoint, params, type(exc).__name__
                )
                continue
            duration_ms = int((self._clock() - started) * 1000)
            headers_quota = self._read_quota(response.headers)
            status = response.status_code

            if status == 429:
                rate_limit_pauses = self._rate_limited(rate_limit_pauses, endpoint, "HTTP 429")
                continue
            if status >= 500:
                transient_failures = self._transient(transient_failures, endpoint, params, f"HTTP {status}")
                continue
            try:
                body = response.json()
            except ValueError:
                transient_failures = self._transient(
                    transient_failures, endpoint, params, f"HTTP {status}, JSON illisible"
                )
                continue
            if status >= 400:
                raise HttpError(f"HTTP {status} sur {endpoint} {params}")
            if not isinstance(body, dict):
                raise HttpError(f"Réponse inattendue (pas un objet JSON) sur {endpoint} {params}")

            errors = normalize_errors(body.get("errors"))
            if isinstance(errors, dict):
                if "rateLimit" in errors:
                    rate_limit_pauses = self._rate_limited(rate_limit_pauses, endpoint, "errors.rateLimit")
                    continue
                if "requests" in errors:
                    self.remaining_day = 0
                    raise DailyQuotaExhausted(f"Quota du jour épuisé (errors.requests) : {errors['requests']}")
                if "token" in errors:
                    raise AuthenticationError(
                        "Clé API refusée (errors.token) : vérifier API_FOOTBALL_KEY dans .env."
                    )

            return ApiResponse(
                endpoint=endpoint,
                params=params,
                http_status=status,
                headers_quota=headers_quota,
                body=body,
                fetched_at=fetched_at,
                duration_ms=duration_ms,
            )

    def status(self) -> ApiResponse:
        """`/status` : état du compte et quota consommé du jour.

        Le corps donne `requests.current` et `requests.limit_day` : on en
        déduit le quota restant même si les en-têtes sont absents.
        """
        response = self.get("/status", {})
        body_response = response.body.get("response")
        if isinstance(body_response, dict):
            requests_info = body_response.get("requests") or {}
            current = to_int(requests_info.get("current"))
            limit = to_int(requests_info.get("limit_day"))
            if current is not None and limit is not None:
                self.remaining_day = limit - current
        return response

    def _check_can_send(self) -> None:
        if self.max_requests is not None and self.requests_made >= self.max_requests:
            raise RequestBudgetExhausted(
                f"Nombre maximal de requêtes du lancement atteint ({self.max_requests})."
            )
        if self.remaining_day is not None and self.remaining_day <= self.reserve:
            raise QuotaReserveReached(
                f"Quota du jour restant ({self.remaining_day}) <= réserve ({self.reserve}) : arrêt propre."
            )

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            wait = self._last_request_at + self._min_interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._clock()

    def _read_quota(self, headers) -> dict:
        quota = {name: headers.get(name) for name in QUOTA_HEADERS if headers.get(name) is not None}
        day = to_int(quota.get(DAY_REMAINING))
        if day is not None:
            self.remaining_day = day
        minute = to_int(quota.get(MINUTE_REMAINING))
        if minute is not None:
            self.remaining_minute = minute
        return quota

    def _transient(self, failures: int, endpoint: str, params: dict, reason: str) -> int:
        failures += 1
        if failures >= MAX_ATTEMPTS:
            raise TransientError(f"{reason} après {MAX_ATTEMPTS} tentatives")
        wait = BACKOFF_BASE_SECONDS**failures
        logger.warning("%s sur %s %s : nouvelle tentative dans %s s", reason, endpoint, params, wait)
        self._sleep(wait)
        return failures

    def _rate_limited(self, pauses: int, endpoint: str, reason: str) -> int:
        pauses += 1
        if pauses > MAX_RATE_LIMIT_PAUSES:
            raise TransientError(f"{reason} persistant après {MAX_RATE_LIMIT_PAUSES} pauses")
        logger.warning("%s sur %s : pause de %s s", reason, endpoint, RATE_LIMIT_PAUSE_SECONDS)
        self._sleep(RATE_LIMIT_PAUSE_SECONDS)
        return pauses
