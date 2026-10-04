"""Client HTTP de l'interface : la seule porte entre Streamlit et le reste du projet (ADR-0040).

L'interface ne lit jamais la base et n'importe aucune logique métier : elle appelle l'API locale
(`FP_API_URL`, défaut `http://127.0.0.1:8000`) avec `httpx`. Toute réponse d'erreur devient une
`ApiProblem` lisible (statut HTTP, message, raisons), affichée telle quelle par l'interface.

Pour les tests, `TRANSPORT` remplace le réseau par un faux transport `httpx` (par exemple
`httpx.MockTransport`) : aucun serveur n'est lancé, aucune requête ne sort du processus.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000"
TIMEOUT_S = 60.0  # un premier `GET /matches` à froid construit le contexte d'inférence (environ 7 s mesurées)

TRANSPORT: httpx.BaseTransport | None = None  # faux transport des tests ; None = vrai réseau local


def api_url() -> str:
    return os.environ.get("FP_API_URL", DEFAULT_API_URL).rstrip("/")


@dataclass
class ApiProblem(Exception):
    """Erreur de l'API (403, 404, 409, 501, 503…) ou API injoignable (`status` = None)."""

    status: int | None
    detail: str
    reasons: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.detail


class ApiClient:
    """Une méthode par route du rapport F.6 ; chaque appel renvoie le JSON décodé ou lève `ApiProblem`."""

    def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url or api_url()
        self._transport = transport if transport is not None else TRANSPORT

    def _request(self, method: str, path: str, **kwargs):
        try:
            with httpx.Client(base_url=self.base_url, timeout=TIMEOUT_S, transport=self._transport) as http:
                response = http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise ApiProblem(
                None,
                f"API injoignable à {self.base_url} ({type(error).__name__}). "
                "Lancer : uv run python -m foot_predictor.api serve",
            ) from error
        if response.is_success:
            return response.json()
        try:
            body = response.json()
        except ValueError:
            body = {}
        detail = body.get("detail") if isinstance(body, dict) else None
        if not isinstance(detail, str):  # erreur de validation 422 : liste de champs refusés
            detail = f"Requête refusée par l'API (HTTP {response.status_code})."
        reasons = body.get("reasons", []) if isinstance(body, dict) else []
        raise ApiProblem(response.status_code, detail, list(reasons))

    def health(self) -> dict:
        return self._request("GET", "/health")

    def competitions(self) -> list[dict]:
        return self._request("GET", "/competitions")

    def matches(self, date: dt.date, mode: str, competitions: list[int] | None = None) -> list[dict]:
        params: dict = {"date": date.isoformat(), "mode": mode}
        if competitions:
            params["competition"] = competitions
        return self._request("GET", "/matches", params=params)

    def availability(self, match_id: int, mode: str) -> dict:
        return self._request("GET", f"/matches/{int(match_id)}/availability", params={"mode": mode})

    def predict(self, match_id: int, mode: str) -> dict:
        """Crée la prédiction (201) ou renvoie celle déjà tracée (200) : la création est idempotente."""
        return self._request("POST", f"/matches/{int(match_id)}/predictions", params={"mode": mode})

    def active_model(self) -> dict:
        return self._request("GET", "/models/active")

    def freshness(self) -> dict:
        return self._request("GET", "/data/freshness")
