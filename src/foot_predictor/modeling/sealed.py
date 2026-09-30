"""Garde-fous du test scellé (ADR-0012, règle 5 ; ADR-0039), vérifiés par `evaluate --sealed-test`.

1. **Code figé** : le tag `pre-scelle-h1` existe, et `git diff pre-scelle-h1 -- <code et expériences>`
   est vide (aucun changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`,
   `experiments/` depuis le tag, ni dans l'arbre de travail).
2. **Une seule fois** : le journal `reports/sealed_tests.md` ne contient pas déjà une évaluation
   terminée pour ce fichier d'expérience.

Un refus n'écrit rien et ne lit aucune donnée scellée.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from foot_predictor.seal import SEALED_TESTS_LOG

FROZEN_TAG = "pre-scelle-h1"
FROZEN_PATHS = ("src/foot_predictor/modeling", "src/foot_predictor/features", "experiments")
REPO_ROOT = Path(__file__).resolve().parents[3]


class SealedTestRefused(RuntimeError):
    """Le test scellé ne peut pas être lancé (code non figé, ou déjà mené à son terme)."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)


def check_frozen(tag: str = FROZEN_TAG, git=_git) -> None:
    """Refuse si le tag manque ou si le code et les expériences ont changé depuis le tag."""
    if git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode != 0:
        raise SealedTestRefused(f"Tag {tag} absent : la liste du test scellé n'est pas figée (ADR-0039).")
    diff = git("diff", "--stat", tag, "--", *FROZEN_PATHS)
    if diff.returncode != 0 or diff.stdout.strip():
        raise SealedTestRefused(
            f"Code ou expériences modifiés depuis {tag} : test scellé refusé (ADR-0039).\n{diff.stdout.strip()}"
        )


def already_evaluated(experiment: str, log_path: Path | None = None) -> bool:
    """Vrai si le journal contient déjà une évaluation scellée terminée pour `experiment`."""
    from foot_predictor.modeling.experiment import SEALED_DONE

    path = log_path or SEALED_TESTS_LOG
    if not path.exists():
        return False
    return any(experiment in line and SEALED_DONE in line for line in path.read_text(encoding="utf-8").splitlines())


def check_sealed_test_allowed(experiment: str, log_path: Path | None = None, git=_git) -> None:
    check_frozen(git=git)
    if already_evaluated(experiment, log_path):
        raise SealedTestRefused(f"{experiment} : test scellé déjà mené à son terme ; il ne se relance pas (ADR-0012).")
