"""Refuse une ligne de `.tex` qui finit par un seul antislash au lieu de « \\\\ ».

Origine : E-053, même famille que E-029 (antislash perdu à l'écriture). Écrit par un
outil qui interprète les antislashs, le passage à la ligne « \\\\ » d'un environnement
`cases` ou `align` devient « \\ » : LaTeX compile sans erreur, mais les lignes se
collent et la formule est fausse.

Refusé : une ligne qui finit par un nombre impair d'antislashs (« \\ », « \\\\\\ »).
Autorisé : « \\\\ » et toute fin de ligne sans antislash.

Usage (pre-commit passe les fichiers modifiés) :

    python -m foot_predictor.outils.latex FICHIER [FICHIER ...]

Code de retour : 0 si tout est propre, 1 sinon (une ligne par fin de ligne refusée).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

# Antislashs en fin de ligne : un nombre impair, précédé d'autre chose qu'un antislash.
LONE_BACKSLASH = re.compile(r"(?<!\\)(?:\\\\)*\\$")


def is_checked(path: str | Path) -> bool:
    """Le fichier fait-il partie du contrôle (extension `.tex`) ?"""
    return Path(path).suffix.lower() == ".tex"


def find_lone_backslashes(text: str) -> list[int]:
    """Numéros (à partir de 1) des lignes qui finissent par un nombre impair d'antislashs."""
    return [number for number, line in enumerate(text.split("\n"), start=1) if LONE_BACKSLASH.search(line.rstrip("\r"))]


def check_files(paths: Iterable[str | Path]) -> list[str]:
    """Messages d'erreur pour les fichiers contrôlés ; les autres sont ignorés."""
    errors = []
    for path in paths:
        if not is_checked(path):
            continue
        text = Path(path).read_bytes().decode("utf-8", errors="replace")
        errors += [
            f"{Path(path).as_posix()}:{line}: ligne finie par un seul antislash" for line in find_lone_backslashes(text)
        ]
    return errors


def main(argv: list[str] | None = None) -> int:
    errors = check_files(sys.argv[1:] if argv is None else argv)
    for error in errors:
        print(error)
    if errors:
        print("Fin de ligne « \\ » au lieu de « \\\\ » (voir E-053) : corriger avec l'éditeur, pas un script.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
