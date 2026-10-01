"""Application FastAPI locale (rapport F.6, ADR-0040) : l'inférence derrière des routes HTTP.

| Route | Rôle | Erreurs |
|---|---|---|
| `GET /health` | vivacité, base, modèle actif | — |
| `GET /competitions` | championnats présents, avec le périmètre du modèle | — |
| `GET /matches?date=&competition=&mode=` | matchs d'une date, statut de disponibilité résumé | 403 date refusée |
| `GET /matches/{id}/availability?horizon=&mode=` | détail par variable | 404, 403, 501 (H2) |
| `POST /matches/{id}/predictions?horizon=&mode=&force=` | calcule et trace (ou renvoie l'existante) | 404, 403, 409, 501 |
| `GET /models/active` | carte d'identité du modèle actif | 503 |
| `GET /data/freshness` | dernière mise à jour de chaque source | — |

Usage local seulement : liaison 127.0.0.1, ni authentification ni CORS ; aucune réponse ne contient
de chemin de fichier, d'URL de base ou de secret. Le contexte d'inférence (table des matchs,
caches) est gardé en mémoire et reconstruit quand la version des données change.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from foot_predictor.api import schemas
from foot_predictor.features.leagues import TOP5
from foot_predictor.inference import models as model_store
from foot_predictor.inference.availability import AVAILABLE, H2_UNAVAILABLE
from foot_predictor.inference.predict import InferenceContext, ReferenceDateRefused, predict_day

REPO_ROOT = Path(__file__).resolve().parents[3]
FOOTBALL_DATA_MANIFEST = REPO_ROOT / "data" / "raw" / "_manifest" / "football_data.jsonl"


class ApiError(Exception):
    def __init__(self, status: int, detail: str, reasons: list[str] | None = None) -> None:
        super().__init__(detail)
        self.status, self.detail, self.reasons = status, detail, reasons or []


class ContextProvider:
    """Contexte d'inférence en cache dans le processus, reconstruit quand `version()` change."""

    def __init__(self, build: Callable[[], InferenceContext], version: Callable[[], str]) -> None:
        self._build, self._version = build, version
        self._context: InferenceContext | None = None
        self._lock = threading.Lock()

    def get(self) -> InferenceContext:
        current = self._version()
        with self._lock:
            if self._context is None or self._context.data_version != current:
                self._context = self._build()
            return self._context


def default_provider() -> ContextProvider:
    from foot_predictor.db.session import get_engine
    from foot_predictor.inference.context import build_context, last_load_run

    engine = get_engine()
    return ContextProvider(lambda: build_context(engine), lambda: f"load_run-{last_load_run(engine)[0]}")


def default_sessions() -> AbstractContextManager:
    from sqlalchemy.orm import Session

    from foot_predictor.db.session import get_engine

    return Session(get_engine())


def _find_match(context: InferenceContext, match_id: int):
    found = context.matches[context.matches["match_id"] == match_id]
    if found.empty:
        raise ApiError(404, f"Match {match_id} inconnu (ou sous scellés : jamais servi avant le test scellé).")
    return found.iloc[0]


def _answer(context: InferenceContext, match_id: int, mode: str, horizon: str) -> dict:
    match = _find_match(context, match_id)
    try:
        (answer,) = predict_day(match["match_day"], mode, context, match_ids=[match_id], horizon=horizon)
    except ReferenceDateRefused as error:
        raise ApiError(403, str(error)) from error
    if answer["status"] == H2_UNAVAILABLE:
        raise ApiError(501, "Horizon H2 (avec composition) : non disponible avant la partie 6.", answer["reasons"])
    return answer


def _summary(answer: dict) -> dict:
    keys = schemas.MatchSummary.model_fields
    return {k: answer[k] for k in keys}


def create_app(
    provider: ContextProvider | None = None,
    sessions: Callable[[], AbstractContextManager] | None = None,
) -> FastAPI:
    """Fabrique : `provider` (contexte d'inférence) et `sessions` (base) sont injectables pour les tests."""
    app = FastAPI(
        title="foot-predictor",
        version="0.6.0.dev0",
        description="Loi du nombre de buts d'un match du top 5, avec sa disponibilité (partie 5, ADR-0040).",
    )
    state = {"provider": provider, "sessions": sessions or default_sessions}

    def context() -> InferenceContext:
        if state["provider"] is None:
            state["provider"] = default_provider()
        return state["provider"].get()

    @app.exception_handler(ApiError)
    async def api_error(_: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(status_code=error.status, content={"detail": error.detail, "reasons": error.reasons})

    @app.get("/health", response_model=schemas.Health)
    def health() -> dict:
        try:
            ctx = context()
            database, version = "ok", ctx.data_version
        except Exception as error:  # noqa: BLE001 - l'état dégradé se dit, il ne plante pas la route
            return {"status": "degraded", "database": f"erreur : {type(error).__name__}", "model": None}
        try:
            model = model_store.load_active(ctx.active_version).version
        except model_store.ModelUnavailable as error:
            return {"status": "degraded", "database": database, "model": str(error), "data_version": version}
        return {"status": "ok", "database": database, "model": model, "data_version": version}

    @app.get("/competitions", response_model=list[schemas.Competition])
    def competitions() -> list[dict]:
        ctx = context()
        unique = ctx.matches.drop_duplicates("competition_id").sort_values("competition_id")
        return [
            {
                "id": int(row.competition_id),
                "name": ctx.competition_names.get(int(row.competition_id)),
                "api_league_id": int(row.api_league_id) if row.api_league_id == row.api_league_id else None,
                "country": getattr(row, "country", None),
                "kind": getattr(row, "competition_kind", None),
                "in_model_scope": int(row.api_league_id) in TOP5 if row.api_league_id == row.api_league_id else False,
            }
            for row in unique.itertuples()
        ]

    @app.get("/matches", response_model=list[schemas.MatchSummary], responses={403: {"model": schemas.Problem}})
    def matches(
        date: dt.date,
        mode: schemas.Mode = "replay",
        competition: Annotated[list[int] | None, Query()] = None,
    ) -> list[dict]:
        ctx = context()
        try:
            answers = predict_day(date, mode, ctx, competition_ids=competition)
        except ReferenceDateRefused as error:
            raise ApiError(403, str(error)) from error
        return [_summary(a) for a in answers]

    @app.get(
        "/matches/{match_id}/availability",
        response_model=schemas.AvailabilityOut,
        responses={403: {"model": schemas.Problem}, 404: {"model": schemas.Problem}, 501: {"model": schemas.Problem}},
    )
    def availability(match_id: int, horizon: schemas.Horizon = "H1", mode: schemas.Mode = "replay") -> dict:
        answer = _answer(context(), match_id, mode, horizon)
        return _summary(answer) | {"variables": answer["availability"]}

    @app.post(
        "/matches/{match_id}/predictions",
        response_model=schemas.PredictionOut,
        status_code=201,
        responses={
            200: {"model": schemas.PredictionOut, "description": "prédiction déjà tracée, renvoyée telle quelle"},
            403: {"model": schemas.Problem}, 404: {"model": schemas.Problem},
            409: {"model": schemas.Problem}, 501: {"model": schemas.Problem},
        },
    )  # fmt: skip
    def create_prediction(
        match_id: int, horizon: schemas.Horizon = "H1", mode: schemas.Mode = "replay", force: bool = False
    ):
        from foot_predictor.inference.store import LivePredictionTooLate, save_prediction

        ctx = context()
        answer = _answer(ctx, match_id, mode, horizon)
        if answer["status"] != AVAILABLE:
            raise ApiError(409, f"Match {match_id} indisponible ({answer['status']}) : aucune prédiction.",
                           answer["reasons"])  # fmt: skip
        reference = dt.date.fromisoformat(answer["date"]) if mode == "replay" else (ctx.today or dt.date.today())
        with state["sessions"]() as session:
            try:
                saved = save_prediction(session, answer, reference, force=force)
            except LivePredictionTooLate as error:
                raise ApiError(409, str(error)) from error
            session.commit()
            info = {"id": saved.prediction.id, "created": saved.created,
                    "created_at": saved.prediction.created_at.isoformat() if saved.prediction.created_at else None}  # fmt: skip
        body = _summary(answer) | {
            "variables": answer["availability"],
            "prediction": answer["prediction"],
            "actual_score": answer["actual_score"],
            "market_reference": answer["market_reference"],
            "saved": info,
        }
        payload = schemas.PredictionOut.model_validate(body).model_dump(mode="json")
        return JSONResponse(status_code=201 if saved.created else 200, content=payload)

    @app.get("/models/active", responses={503: {"model": schemas.Problem}})
    def active_model() -> dict:
        try:
            loaded = model_store.load_active(context().active_version)
        except model_store.ModelUnavailable as error:
            raise ApiError(503, str(error)) from error
        card = dict(loaded.card)
        card.pop("experiment_file", None)  # aucun chemin de fichier dans une réponse
        return card

    @app.get("/data/freshness", response_model=schemas.Freshness)
    def freshness() -> dict:
        ctx = context()
        sources = [
            {
                "source": "staging (référentiel reconstruit par load)",
                "last_update": ctx.freshness.last_update.isoformat() if ctx.freshness.last_update else None,
                "complete_until": ctx.freshness.complete_until.isoformat(),
            },
            football_data_freshness(),
        ]
        return {"data_version": ctx.data_version, "sources": sources}

    return app


def football_data_freshness(manifest: Path = FOOTBALL_DATA_MANIFEST) -> dict:
    """Dernier fichier de football-data stocké (journal de l'ADR-0024) ; le live arrive en 5.10."""
    last = None
    if manifest.exists():
        lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            entry = json.loads(lines[-1])
            last = entry.get("fetched_at") or entry.get("timestamp") or entry.get("date")
    return {
        "source": "football-data (CSV historiques)",
        "last_update": last,
        "complete_until": None,
        "note": "résultats et prochains matchs du live : sous-étape 5.10 (phase B pour les données réelles)",
    }
