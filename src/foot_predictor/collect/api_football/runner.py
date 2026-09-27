"""Exécution de la file de travail (commande `run`).

Pour chaque tâche `pending`, dans l'ordre palier puis priorité :

1. requête via le client (cadence, quota, 429, 5xx : voir `client.py`) ;
2. stockage de la réponse (`rawstore`) : fichier atomique, puis ligne de journal ;
3. classement de la tâche :

| Réponse | Statut |
|---|---|
| `errors` non vide | `failed`, sans nouvelle tentative |
| `results = 0` alors que le type attend des données | `suspect` |
| lot de détails incomplet (ids demandés absents de la réponse) | `suspect` |
| sinon | `done` (et, pour la page 1 de `players`, ajout des pages 2 à N) |
| échec temporaire persistant (après 3 tentatives) | reste `pending`, `failed` au 3e lancement |
| HTTP 4xx | `failed` |

Ordre des écritures : fichier, journal, puis file. Un plantage entre deux
étapes coûte au pire une requête refaite au lancement suivant (nouvelle
version du fichier), jamais une donnée perdue ou un fichier corrompu.

Quand la file est vide, le plan des paliers déjà planifiés est relancé, pour
créer les tâches dérivées des listes qui viennent d'arriver (détails,
entraîneurs, transferts). La collecte s'arrête quand plus rien n'est ajouté,
ou proprement sur la réserve de quota, le quota du jour épuisé, ou
`--max-requests`.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE, tasks
from foot_predictor.collect.api_football.client import (
    DAY_REMAINING,
    MINUTE_REMAINING,
    ApiFootballClient,
    ApiResponse,
    CollectStop,
    HttpError,
    TransientError,
    to_int,
)
from foot_predictor.collect.api_football.plan import CollectConfig, Planner
from foot_predictor.collect.api_football.queue import QueuedTask, WorkQueue
from foot_predictor.rawstore.manifest import append_entry, entry_for_stored
from foot_predictor.rawstore.store import StoredFile, build_envelope, write_envelope

logger = logging.getLogger(__name__)

STATUS_REL_DIR = f"{SOURCE}/status"


def manifest_extra(envelope: dict) -> dict:
    """Champs propres à API-FOOTBALL ajoutés à chaque ligne de journal.

    Servent aussi à la reconstruction du journal (`rebuild-manifest`).
    """
    headers = envelope.get("headers_quota") or {}
    request = envelope["request"]
    body = envelope.get("body") if isinstance(envelope.get("body"), dict) else {}
    extra = {
        "quota_remaining_day": to_int(headers.get(DAY_REMAINING)),
        "quota_remaining_minute": to_int(headers.get(MINUTE_REMAINING)),
    }
    if request["endpoint"] == "/status" and extra["quota_remaining_day"] is None:
        info = (body.get("response") or {}).get("requests") if isinstance(body.get("response"), dict) else None
        if info:
            current, limit = to_int(info.get("current")), to_int(info.get("limit_day"))
            if current is not None and limit is not None:
                extra["quota_remaining_day"] = limit - current
    if request["endpoint"] == "/fixtures" and "ids" in (request.get("params") or {}):
        extra["fixture_ids"] = returned_fixture_ids(body)
    return extra


def returned_fixture_ids(body: dict) -> list[int]:
    ids = []
    for item in body.get("response") or []:
        fixture_id = (item.get("fixture") or {}).get("id") if isinstance(item, dict) else None
        if fixture_id is not None:
            ids.append(int(fixture_id))
    return sorted(ids)


def store_response(raw_dir: Path, rel_dir: str, stem: str, response: ApiResponse) -> StoredFile:
    envelope = build_envelope(
        endpoint=response.endpoint,
        params=response.params,
        fetched_at=response.fetched_at,
        http_status=response.http_status,
        headers_quota=response.headers_quota,
        body=response.body,
    )
    stored = write_envelope(raw_dir, rel_dir, stem, envelope, response.fetched_at)
    entry = entry_for_stored(
        envelope, stored, source=SOURCE, duration_ms=response.duration_ms, extra=manifest_extra(envelope)
    )
    append_entry(raw_dir, SOURCE, entry)
    return stored


def classify(task: QueuedTask, response: ApiResponse) -> tuple[str, str | None]:
    """Statut de la tâche d'après la réponse : (statut, raison)."""
    if response.errors:
        return "failed", f"errors : {response.errors}"
    results = response.results or 0
    if task.expects_results and results == 0:
        return "suspect", "results = 0 alors que des données sont attendues"
    if task.task_type == "fixtures_detail":
        requested = set(tasks.parse_ids(task.params["ids"]))
        missing = sorted(requested - set(returned_fixture_ids(response.body)))
        if missing:
            return "suspect", f"lot incomplet : {len(missing)} match(s) absent(s) {missing}"
    return "done", None


@dataclass
class RunReport:
    requests: int = 0
    outcomes: Counter = field(default_factory=Counter)
    replanned: int = 0
    stop_reason: str | None = None


class Runner:
    def __init__(
        self,
        client: ApiFootballClient,
        queue: WorkQueue,
        raw_dir: Path,
        config: CollectConfig,
        *,
        replan: bool = True,
    ) -> None:
        self.client = client
        self.queue = queue
        self.raw_dir = Path(raw_dir)
        self.config = config
        self.replan = replan
        self.report = RunReport()
        self._retry_later: set[int] = set()

    def run(self) -> RunReport:
        try:
            # /status d'abord : quota restant connu avant la première requête de données.
            store_response(self.raw_dir, STATUS_REL_DIR, "status", self.client.status())
            while True:
                pending = self.queue.list_pending(exclude_ids=self._retry_later)
                if not pending:
                    if not self.replan or self._replan() == 0:
                        break
                    continue
                for task in pending:
                    self._execute(task)
        except CollectStop as exc:
            self.report.stop_reason = str(exc)
            logger.warning("Arrêt propre : %s", exc)
        finally:
            self.report.requests = self.client.requests_made
        return self.report

    def _execute(self, task: QueuedTask) -> None:
        label = f"[{task.tier}] {task.task_type} {task.params}"
        try:
            response = self.client.get(task.endpoint, task.params)
        except TransientError as exc:
            status = self.queue.record_transient_failure(task.id, str(exc))
            self._retry_later.add(task.id)
            self.report.outcomes[f"échec temporaire ({status})"] += 1
            logger.warning("%s : %s, reste %s", label, exc, status)
            return
        except HttpError as exc:
            self.queue.mark_failed(task.id, str(exc))
            self.report.outcomes["failed"] += 1
            logger.warning("%s : %s", label, exc)
            return

        stored = store_response(self.raw_dir, task.rel_dir, task.stem, response)
        status, reason = classify(task, response)
        if status == "done":
            self.queue.mark_done(task.id, stored.relative_path)
            if task.task_type == "players":
                self._enqueue_next_pages(task, response)
        elif status == "failed":
            self.queue.mark_failed(task.id, reason or "", stored.relative_path)
        else:
            self.queue.mark_suspect(task.id, reason or "", stored.relative_path)
        self.report.outcomes[status] += 1
        log = logger.info if status == "done" else logger.warning
        log("%s : %s (%s résultats, quota du jour restant %s)%s", label, status, response.results,
            self.client.remaining_day, f" ; {reason}" if reason else "")

    def _enqueue_next_pages(self, task: QueuedTask, response: ApiResponse) -> None:
        paging = response.body.get("paging") or {}
        total, page = to_int(paging.get("total")), task.params.get("page", 1)
        if page != 1 or not total or total <= 1:
            return
        league, season = task.params["league"], task.params["season"]
        added = self.queue.add(tasks.players_task(task.tier, league, season, p) for p in range(2, total + 1))
        logger.info("[%s] players league=%s season=%s : %s pages ajoutées", task.tier, league, season, added)

    def _replan(self) -> int:
        planner = Planner(self.config, self.raw_dir, self.queue)
        added = 0
        for tier in self.queue.planned_tiers():
            report = planner.plan(tier)
            added += report.total_added
            if report.total_added:
                logger.info("Plan %s relancé : %s", tier, dict(report.added))
        self.report.replanned += added
        return added


def dry_run_lines(queue: WorkQueue) -> list[str]:
    """Ce que `run` ferait, sans aucun appel réseau."""
    pending = Counter()
    for tier, task_type, status, count in queue.counts():
        if status == "pending":
            pending[(tier, task_type)] += count
    lines = ["Simulation : aucune requête envoyée.", ""]
    if not pending:
        lines.append("Aucune tâche pending. Lancer d'abord : plan --palier P1")
        return lines
    lines.append(f"{'Palier':<7}{'Type':<17}{'Requêtes':>9}")
    for (tier, task_type), count in sorted(pending.items(), key=lambda kv: (kv[0][0], tasks.PRIORITY[kv[0][1]])):
        lines.append(f"{tier:<7}{task_type:<17}{count:>9}")
    lines += [
        f"{'Total':<24}{sum(pending.values()):>9}",
        "",
        "+ 1 requête /status au démarrage.",
        "Les tâches dérivées (lots de détails, entraîneurs, transferts, pages 2 à N",
        "des joueurs) sont créées au fil du run, quand leurs listes arrivent.",
    ]
    return lines
