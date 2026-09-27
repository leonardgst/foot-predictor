"""File de travail reprenable : `data/raw/_queue/api_football.sqlite` (rapport G.6).

SQLite (bibliothèque standard) plutôt qu'une table Postgres : la collecte ne
dépend ainsi ni de Docker ni de la base (ADR-0004).

Statuts d'une tâche :

- `pending` : à faire. Seul statut traité par `run` ;
- `done` : réponse stockée et conforme ;
- `failed` : `errors` non vide, erreur HTTP 4xx, ou échec temporaire répété
  sur 3 lancements. Aucune nouvelle tentative automatique ;
- `suspect` : réponse stockée, mais `results = 0` alors qu'on attendait des
  données, ou lot de détails incomplet. À revoir à la main.

`requeue` remet des tâches `failed` ou `suspect` en `pending`, après examen.

La table `deferred_fixtures` liste les matchs à statut non terminal (à venir,
reportés, interrompus...) : ils ne sont pas mis en lot, et serviront à une
recollecte ultérieure.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from foot_predictor.collect.api_football.tasks import Task, parse_ids

QUEUE_RELATIVE_PATH = Path("_queue") / "api_football.sqlite"
STATUSES = ("pending", "done", "failed", "suspect")
MAX_TASK_ATTEMPTS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL,
    task_type TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    params TEXT NOT NULL,
    rel_dir TEXT NOT NULL,
    stem TEXT NOT NULL,
    expects_results INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'done', 'failed', 'suspect')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    file TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tasks_pending ON tasks (status, tier, priority, id);
CREATE TABLE IF NOT EXISTS deferred_fixtures (
    fixture_id INTEGER PRIMARY KEY,
    league INTEGER NOT NULL,
    season INTEGER NOT NULL,
    status_short TEXT,
    fixture_date TEXT,
    seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS planned_tiers (
    tier TEXT PRIMARY KEY,
    planned_at TEXT NOT NULL
);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class QueuedTask:
    id: int
    tier: str
    task_type: str
    endpoint: str
    params: dict
    rel_dir: str
    stem: str
    expects_results: bool
    status: str
    attempts: int
    last_error: str | None
    file: str | None


class WorkQueue:
    def __init__(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    @classmethod
    def in_raw_dir(cls, raw_dir: Path) -> WorkQueue:
        return cls(Path(raw_dir) / QUEUE_RELATIVE_PATH)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> WorkQueue:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- ajout et lecture ------------------------------------------------

    def add(self, tasks: Iterable[Task]) -> int:
        """Ajoute les tâches absentes (clé canonique) ; renvoie le nombre ajouté."""
        now = _now()
        rows = [
            (t.key, t.tier, t.task_type, t.endpoint, t.params_json(), t.rel_dir, t.stem,
             int(t.expects_results), t.priority, now, now)
            for t in tasks
        ]
        before = self._conn.total_changes
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO tasks (key, tier, task_type, endpoint, params, rel_dir, stem,"
                " expects_results, priority, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return self._conn.total_changes - before

    def contains(self, task: Task) -> bool:
        return self._conn.execute("SELECT 1 FROM tasks WHERE key = ?", (task.key,)).fetchone() is not None

    def status_of(self, task: Task) -> str | None:
        row = self._conn.execute("SELECT status FROM tasks WHERE key = ?", (task.key,)).fetchone()
        return row["status"] if row else None

    def list_pending(self, exclude_ids: Iterable[int] = ()) -> list[QueuedTask]:
        excluded = set(exclude_ids)
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY tier, priority, id"
        ).fetchall()
        return [self._to_task(row) for row in rows if row["id"] not in excluded]

    def get(self, task_id: int) -> QueuedTask:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._to_task(row)

    def detail_fixture_ids(self) -> set[int]:
        """Identifiants de tous les matchs déjà mis en lot, quel que soit le statut."""
        ids: set[int] = set()
        for row in self._conn.execute("SELECT params FROM tasks WHERE task_type = 'fixtures_detail'"):
            ids.update(parse_ids(json.loads(row["params"])["ids"]))
        return ids

    # --- changements de statut ----------------------------------------------

    def mark_done(self, task_id: int, file: str) -> None:
        self._set(task_id, "done", file=file, error=None)

    def mark_failed(self, task_id: int, error: str, file: str | None = None) -> None:
        self._set(task_id, "failed", file=file, error=error)

    def mark_suspect(self, task_id: int, reason: str, file: str) -> None:
        self._set(task_id, "suspect", file=file, error=reason)

    def record_transient_failure(self, task_id: int, error: str) -> str:
        """Échec temporaire (5xx, délai) : la tâche reste `pending` jusqu'à
        `MAX_TASK_ATTEMPTS` lancements, puis passe `failed`. Renvoie le statut."""
        task = self.get(task_id)
        attempts = task.attempts + 1
        status = "failed" if attempts >= MAX_TASK_ATTEMPTS else "pending"
        with self._conn:
            self._conn.execute(
                "UPDATE tasks SET status = ?, attempts = ?, last_error = ?, updated_at = ? WHERE id = ?",
                (status, attempts, error, _now(), task_id),
            )
        return status

    def requeue(self, status: str, task_type: str | None = None) -> int:
        """Remet en `pending` les tâches `failed` ou `suspect` (tentatives à zéro).
        La dernière erreur est conservée pour mémoire."""
        if status not in ("failed", "suspect"):
            raise ValueError("Seules les tâches failed ou suspect peuvent être remises en file.")
        query = "UPDATE tasks SET status = 'pending', attempts = 0, updated_at = ? WHERE status = ?"
        args: list = [_now(), status]
        if task_type:
            query += " AND task_type = ?"
            args.append(task_type)
        with self._conn:
            return self._conn.execute(query, args).rowcount

    def reopen(self, keys: Iterable[str]) -> int:
        """Remet en `pending` des tâches `done` ou `suspect`, pour les rejouer
        (commande `refresh`). La réponse précédente reste sur le disque : la
        nouvelle sera une nouvelle version horodatée du fichier. Une tâche
        `failed` n'est pas concernée : elle relève de `requeue`, après examen."""
        now = _now()
        reopened = 0
        with self._conn:
            for key in keys:
                reopened += self._conn.execute(
                    "UPDATE tasks SET status = 'pending', attempts = 0, updated_at = ?"
                    " WHERE key = ? AND status IN ('done', 'suspect')",
                    (now, key),
                ).rowcount
        return reopened

    def _set(self, task_id: int, status: str, *, file: str | None, error: str | None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE tasks SET status = ?, file = COALESCE(?, file), last_error = ?,"
                " attempts = attempts + 1, updated_at = ? WHERE id = ?",
                (status, file, error, _now(), task_id),
            )

    # --- matchs non terminaux et paliers ---------------------------------------

    def add_deferred(self, rows: Iterable[tuple[int, int, int, str | None, str | None]]) -> None:
        """(fixture_id, league, season, statut court, date) ; remplace l'état précédent."""
        now = _now()
        with self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO deferred_fixtures VALUES (?, ?, ?, ?, ?, ?)",
                [(*row, now) for row in rows],
            )

    def remove_deferred(self, fixture_ids: Iterable[int]) -> None:
        with self._conn:
            self._conn.executemany(
                "DELETE FROM deferred_fixtures WHERE fixture_id = ?", [(i,) for i in fixture_ids]
            )

    def overdue_deferred(self, season: int, leagues: Iterable[int], now: dt.datetime) -> dict[int, int]:
        """Matchs non terminaux dont la date est passée, par compétition.

        Ce sont ceux qu'une nouvelle liste peut faire passer à « terminé » :
        leur nombre borne le coût en lots de détails d'un rafraîchissement.
        """
        wanted = set(leagues)
        counts: dict[int, int] = {}
        for league, date in self._conn.execute(
            "SELECT league, fixture_date FROM deferred_fixtures WHERE season = ?", (season,)
        ):
            if league not in wanted or not date:
                continue
            try:
                kickoff = dt.datetime.fromisoformat(date)
            except ValueError:
                continue
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=dt.timezone.utc)
            if kickoff < now:
                counts[league] = counts.get(league, 0) + 1
        return counts

    def deferred_summary(self) -> list[tuple[str | None, int]]:
        return [
            (row[0], row[1])
            for row in self._conn.execute(
                "SELECT status_short, COUNT(*) FROM deferred_fixtures GROUP BY status_short ORDER BY 2 DESC, 1"
            )
        ]

    def mark_tier_planned(self, tier: str) -> None:
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO planned_tiers VALUES (?, ?)", (tier, _now()))

    def planned_tiers(self) -> list[str]:
        return [row[0] for row in self._conn.execute("SELECT tier FROM planned_tiers ORDER BY tier")]

    # --- suivi ---------------------------------------------------------------

    def counts(self) -> list[tuple[str, str, str, int]]:
        """(palier, type, statut, nombre)."""
        return [
            tuple(row)
            for row in self._conn.execute(
                "SELECT tier, task_type, status, COUNT(*) FROM tasks"
                " GROUP BY tier, task_type, status ORDER BY tier, MIN(priority), status"
            )
        ]

    def problems(self, limit: int = 10) -> list[QueuedTask]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status IN ('failed', 'suspect')"
            " OR (status = 'pending' AND last_error IS NOT NULL)"
            " ORDER BY updated_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._to_task(row) for row in rows]

    @staticmethod
    def _to_task(row: sqlite3.Row) -> QueuedTask:
        return QueuedTask(
            id=row["id"],
            tier=row["tier"],
            task_type=row["task_type"],
            endpoint=row["endpoint"],
            params=json.loads(row["params"]),
            rel_dir=row["rel_dir"],
            stem=row["stem"],
            expects_results=bool(row["expects_results"]),
            status=row["status"],
            attempts=row["attempts"],
            last_error=row["last_error"],
            file=row["file"],
        )
