"""Garde-fous du test scellé (ADR-0012, règle 5 ; ADR-0039, ADR-0050), vérifiés par `evaluate --sealed-test`.

Un test scellé par version, chacun avec sa liste figée : `experiments/scelle_<v>.yaml`, figée par
le tag `pre-scelle-<v>` (`h1` : MVP ; `h2` : version intermédiaire). Le nom du fichier désigne la
version ; un autre nom est refusé.

1. **Code figé** : le tag de la version existe, et `git diff <tag> -- <chemins gelés>` est vide
   (aucun changement depuis le tag, ni dans l'arbre de travail). Chemins gelés : `modeling/`,
   `features/` et `experiments/` ; pour H2, `seal.py` en plus (ADR-0050).
2. **Une seule fois** : le journal `reports/sealed_tests.md` ne contient pas déjà une évaluation
   terminée pour ce fichier d'expérience.

Un refus n'écrit rien et ne lit aucune donnée scellée.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from foot_predictor.seal import SEALED_TESTS_LOG

H1_FROZEN_PATHS = ("src/foot_predictor/modeling", "src/foot_predictor/features", "experiments")
FROZEN = {
    "h1": ("pre-scelle-h1", H1_FROZEN_PATHS),
    "h2": ("pre-scelle-h2", (*H1_FROZEN_PATHS, "src/foot_predictor/seal.py")),
}
"""Version → (tag de la liste figée, chemins gelés jusqu'au test). H1 : inchangé depuis `pre-scelle-h1`."""
REPO_ROOT = Path(__file__).resolve().parents[3]


class SealedTestRefused(RuntimeError):
    """Le test scellé ne peut pas être lancé (code non figé, ou déjà mené à son terme)."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)


def frozen_list(experiment: str) -> tuple[str, tuple[str, ...]]:
    """Tag et chemins gelés de la version que désigne `experiment` (`…/scelle_<v>.yaml`)."""
    match = re.fullmatch(r"scelle_(h\d+)\.yaml", Path(experiment).name)
    if match is None or match[1] not in FROZEN:
        raise SealedTestRefused(
            f"{experiment} : aucune liste figée de test scellé ne porte ce nom "
            f"(attendu : experiments/scelle_<version>.yaml, versions {', '.join(FROZEN)})."
        )
    return FROZEN[match[1]]


def check_frozen(experiment: str, git=_git) -> None:
    """Refuse si le tag de la version manque, ou si le code et les expériences ont changé depuis ce tag."""
    tag, paths = frozen_list(experiment)
    if git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode != 0:
        raise SealedTestRefused(f"Tag {tag} absent : la liste du test scellé n'est pas figée (ADR-0039, ADR-0050).")
    diff = git("diff", "--stat", tag, "--", *paths)
    if diff.returncode != 0 or diff.stdout.strip():
        raise SealedTestRefused(
            f"Code ou expériences modifiés depuis {tag} : test scellé refusé (ADR-0039, ADR-0050).\n"
            f"{diff.stdout.strip()}"
        )


def already_evaluated(experiment: str, log_path: Path | None = None) -> bool:
    """Vrai si le journal contient déjà une évaluation scellée terminée pour `experiment`."""
    from foot_predictor.modeling.experiment import SEALED_DONE

    path = log_path or SEALED_TESTS_LOG
    if not path.exists():
        return False
    return any(experiment in line and SEALED_DONE in line for line in path.read_text(encoding="utf-8").splitlines())


def check_sealed_test_allowed(experiment: str, log_path: Path | None = None, git=_git) -> None:
    check_frozen(experiment, git=git)
    if already_evaluated(experiment, log_path):
        raise SealedTestRefused(f"{experiment} : test scellé déjà mené à son terme ; il ne se relance pas (ADR-0012).")
