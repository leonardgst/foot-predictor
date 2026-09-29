"""Verrou de collecte : une seule commande écrit dans un dossier brut à la fois.

Pourquoi : `run`, `refresh`, `t60`... écrivent dans les mêmes fichiers (file
SQLite, journal). Deux commandes en même temps, par exemple une tâche
planifiée et une commande lancée à la main, entremêleraient leurs écritures.
Un `git pull` pendant une collecte changerait le code en cours d'exécution.

Mécanisme, choisi pour sa simplicité sous Windows : un fichier
`<raw_dir>/_lock/collecte.lock`, créé de façon **atomique** (`O_CREAT |
O_EXCL` : le système refuse la création si le fichier existe déjà). Il
contient le PID, la commande, l'horodatage et la machine, en JSON. Il est
supprimé à la fin de la commande, même en cas d'erreur.

Verrou **périmé** : le processus qui le tient n'existe plus (plantage,
portable éteint), ou le verrou a plus de `STALE_AFTER` (garde-fou contre la
réutilisation d'un PID par Windows). Un verrou périmé est remplacé, avec un
avertissement.

Vérification avant un `git pull` dans le dossier principal :

    uv run python -m foot_predictor.collect.api_football lock-status

Code de retour 0 : libre (ou périmé) ; 1 : une commande tourne, ne pas faire
de `git pull`.
"""
# Remarque : `lock-status` ne supprime jamais un verrou ; seul `acquire`
# remplace un verrou périmé, au moment où une commande en a besoin.
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_RELATIVE_PATH = Path("_lock") / "collecte.lock"
# Le journal T-60 tient le verrou toute une journée de matchs (environ 12 h).
STALE_AFTER = dt.timedelta(hours=18)


class LockHeldError(RuntimeError):
    """Une autre commande tient le verrou."""


def pid_alive(pid: int) -> bool:
    """Le processus existe-t-il encore ?

    Sous Windows, `os.kill(pid, 0)` **termine** le processus : on interroge
    donc le noyau (`OpenProcess`, puis `GetExitCodeProcess`).
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False  # processus inexistant (ou inaccessible : traité comme mort)
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # POSIX : signal 0, aucun effet sur le processus
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(frozen=True)
class LockInfo:
    pid: int
    command: str
    started_at: dt.datetime
    host: str

    def describe(self) -> str:
        return f"« {self.command} », PID {self.pid}, depuis le {self.started_at:%Y-%m-%d %H:%M} UTC ({self.host})"


def lock_path(raw_dir: Path) -> Path:
    return Path(raw_dir) / LOCK_RELATIVE_PATH


def read_lock(raw_dir: Path) -> LockInfo | None:
    """Contenu du verrou, ou None s'il est absent. Un fichier illisible est
    considéré comme tenu depuis sa date de modification par un PID inconnu (0)."""
    path = lock_path(raw_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LockInfo(int(data["pid"]), str(data["command"]),
                        dt.datetime.fromisoformat(data["started_at"]), str(data.get("host", "?")))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        try:
            mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        except FileNotFoundError:
            return None
        return LockInfo(0, "inconnue (verrou illisible)", mtime, "?")


UNREADABLE_GRACE = dt.timedelta(minutes=1)


def is_stale(info: LockInfo, now: dt.datetime, alive: Callable[[int], bool] = pid_alive) -> bool:
    """Verrou abandonné ?

    - plus vieux que `STALE_AFTER` : oui ;
    - illisible (PID 0) : oui après une minute. Juste après sa création
      atomique, le fichier est encore vide : ce n'est pas un abandon ;
    - tenu sur cette machine par un processus qui n'existe plus : oui.
    """
    age = now - info.started_at
    if age > STALE_AFTER:
        return True
    if info.pid == 0:
        return age > UNREADABLE_GRACE
    return info.host == socket.gethostname() and not alive(info.pid)


class CollectLock:
    """Verrou d'un dossier brut, utilisable avec `with`.

        with CollectLock(raw_dir, "run --max-requests 100"):
            ...

    `wait` : durée maximale d'attente si le verrou est tenu (tâches planifiées :
    le T-60 attend la fin d'un `refresh`). Sans attente, `LockHeldError`.
    """

    def __init__(
        self,
        raw_dir: Path,
        command: str,
        *,
        wait: dt.timedelta = dt.timedelta(0),
        poll_seconds: float = 30.0,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
        alive: Callable[[int], bool] = pid_alive,
        pid: int | None = None,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.command = command
        self.wait = wait
        self.poll_seconds = poll_seconds
        self._now = now
        self._sleep = sleep
        self._alive = alive
        self.pid = pid if pid is not None else os.getpid()
        self.acquired = False

    def acquire(self) -> None:
        path = lock_path(self.raw_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self._now() + self.wait
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                info = read_lock(self.raw_dir)
                if info is None:
                    continue  # libéré entre-temps : nouvel essai immédiat
                if is_stale(info, self._now(), self._alive):
                    # Relu juste avant de supprimer : si une autre commande vient
                    # de le remplacer, on ne supprime pas son verrou tout neuf.
                    if read_lock(self.raw_dir) == info:
                        logger.warning("Verrou périmé remplacé : %s", info.describe())
                        path.unlink(missing_ok=True)
                    continue
                if self._now() >= deadline:
                    raise LockHeldError(f"Dossier brut occupé par {info.describe()}. "
                                        "Attendre la fin de cette commande (voir lock-status).") from None
                self._sleep(self.poll_seconds)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": self.pid, "command": self.command, "host": socket.gethostname(),
                           "started_at": self._now().isoformat()}, handle)
            self.acquired = True
            return

    def release(self) -> None:
        if not self.acquired:
            return
        info = read_lock(self.raw_dir)
        if info is not None and info.pid == self.pid:
            lock_path(self.raw_dir).unlink(missing_ok=True)
        self.acquired = False

    def __enter__(self) -> CollectLock:
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
