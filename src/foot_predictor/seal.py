"""Scellé technique de l'ADR-0012 : frontière unique des matchs sous scellés.

Tout match joué à partir du 1er juillet 2025 (date UTC du coup d'envoi ; pour un match
« hors API », date de football-data) est sous scellés. Pendant le développement, on ne
lit ni ses scores, ni ses tirs, ni son xG : présence et décomptes seulement.

Ce module porte :

- `SEAL_DATE`, la date du scellé, écrite **une seule fois** dans tout le code ;
- `check_seal`, qui refuse un jeu de matchs franchissant la frontière, sauf avec
  `sealed_test=True` ;
- le journal versionné des usages de `sealed_test=True` (`reports/sealed_tests.md`) :
  chaque usage y ajoute une ligne (date, commit, fichier d'expérience, résultat).

La lecture des matchs passe par `foot_predictor.features.sources`, qui filtre à la
source (SQL) ; `check_seal` y sert de seconde barrière, après la requête.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

SEAL_DATE = dt.date(2025, 7, 1)
"""Premier jour sous scellés (inclus). Un match du 30 juin 2025 est lisible, un match du 1er juillet non."""

SEAL_TIMESTAMP = pd.Timestamp(SEAL_DATE, tz="UTC")
"""La même frontière en horodatage UTC : un coup d'envoi est scellé s'il est `>= SEAL_TIMESTAMP`."""

REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_TESTS_LOG = REPO_ROOT / "reports" / "sealed_tests.md"

LOG_HEADER = """# Journal des tests scellés (ADR-0012)

Chaque usage de l'option `sealed_test=True` (ou `--sealed-test`) ajoute une ligne à ce fichier,
automatiquement, par `foot_predictor.seal.check_seal`. Le test scellé se lance **une fois par
version** (MVP, puis version intermédiaire) ; le résultat est publié tel quel, même décevant.
Un usage absent de ce journal est une levée du scellé à constater dans une nouvelle ADR.

| Date (UTC) | Commit | Fichier d'expérience | Résultat |
|---|---|---|---|
"""


class SealViolation(RuntimeError):
    """Un jeu de matchs contient au moins un match sous scellés, sans `sealed_test=True`."""


def _as_utc_timestamps(dates: Iterable) -> pd.Series:
    """Convertit dates ou horodatages en horodatages UTC (une date seule vaut minuit UTC)."""
    series = pd.Series(list(dates) if not isinstance(dates, pd.Series) else dates)
    if series.empty:
        return pd.Series([], dtype="datetime64[ns, UTC]")
    return pd.to_datetime(series, utc=True)


def count_sealed(dates: Iterable) -> int:
    """Nombre de matchs sous scellés dans `dates` (décompte seulement : aucune autre information)."""
    return int((_as_utc_timestamps(dates) >= SEAL_TIMESTAMP).sum())


def check_seal(
    dates: Iterable,
    *,
    sealed_test: bool = False,
    experiment: str | None = None,
    result: str = "accès autorisé, résultat à compléter",
    log_path: Path | None = None,
) -> int:
    """Refuse tout jeu de matchs qui franchit la frontière du scellé.

    - Sans `sealed_test` : lève `SealViolation` dès qu'une date est `>= SEAL_DATE`.
      Le message ne donne que le **nombre** de matchs scellés, jamais leur contenu.
    - Avec `sealed_test=True` : exige `experiment` (le fichier d'expérience commité) et
      ajoute une ligne au journal `log_path` (par défaut `reports/sealed_tests.md`),
      même si aucun match scellé n'est présent : c'est l'usage de l'option qui est journalisé.

    Renvoie le nombre de matchs scellés présents.
    """
    n_sealed = count_sealed(dates)
    if not sealed_test:
        if n_sealed:
            raise SealViolation(
                f"{n_sealed} match(s) joué(s) à partir du {SEAL_DATE.isoformat()} : sous scellés (ADR-0012). "
                "Les lire exige sealed_test=True, journalisé dans reports/sealed_tests.md."
            )
        return 0
    if not experiment:
        raise SealViolation("sealed_test=True exige le fichier d'expérience (experiment=...), pour le journal.")
    append_log_line(experiment=experiment, result=f"{result} ({n_sealed} match(s) scellé(s) lus)", log_path=log_path)
    return n_sealed


def _current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def append_log_line(*, experiment: str, result: str, log_path: Path | None = None) -> None:
    """Ajoute une ligne au journal des tests scellés (le crée avec son en-tête s'il n'existe pas)."""
    path = log_path or SEALED_TESTS_LOG
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(LOG_HEADER, encoding="utf-8")
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M")
    cells = [now, _current_commit(), experiment, result]
    line = "| " + " | ".join(c.replace("|", "/") for c in cells) + " |\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
