"""Refuse les tabulations et les caractères de contrôle dans les fichiers texte du dépôt.

Origine : E-029 (et les « \\n » cassés de la partie 1). Un fichier réécrit par un
script, avec une chaîne contenant des antislashs, peut recevoir une tabulation à la
place de « \\t » : la commande documentée ne marche plus, sans que rien ne le signale.

Autorisés : saut de ligne (LF) et retour chariot (CR, pour les fins de ligne CRLF
des `.cmd`). Refusés : tous les autres caractères de contrôle ASCII (0x00 à 0x1F,
dont la tabulation, et 0x7F).

Usage (pre-commit passe les fichiers modifiés) :

    python -m foot_predictor.outils.caracteres FICHIER [FICHIER ...]

Code de retour : 0 si tout est propre, 1 sinon (une ligne par caractère trouvé).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

# Extensions contrôlées (partie 2, sous-étape 2.1).
EXTENSIONS = frozenset({".md", ".py", ".yaml", ".yml", ".cmd"})
# Documents d'avant le cadrage, conservés tels quels (ADR-0014).
EXCLUDED_PREFIXES = ("docs/archives/",)

FORBIDDEN = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]")
NAMES = {"\t": "tabulation", "\x0b": "tabulation verticale", "\x0c": "saut de page", "\x7f": "DEL"}


def is_checked(path: str | Path) -> bool:
    """Le fichier fait-il partie du contrôle (extension, hors archives) ?"""
    posix = Path(path).as_posix()
    return Path(posix).suffix.lower() in EXTENSIONS and not posix.startswith(EXCLUDED_PREFIXES)


def describe(char: str) -> str:
    return NAMES.get(char, f"caractère de contrôle U+{ord(char):04X}")


def find_forbidden(text: str) -> list[tuple[int, int, str]]:
    """(ligne, colonne, description) de chaque caractère refusé ; lignes et colonnes à partir de 1."""
    found = []
    for number, line in enumerate(text.split("\n"), start=1):
        for match in FORBIDDEN.finditer(line):
            found.append((number, match.start() + 1, describe(match.group())))
    return found


def check_files(paths: Iterable[str | Path]) -> list[str]:
    """Messages d'erreur pour les fichiers contrôlés ; les autres sont ignorés."""
    errors = []
    for path in paths:
        if not is_checked(path):
            continue
        text = Path(path).read_bytes().decode("utf-8", errors="replace")
        errors += [f"{Path(path).as_posix()}:{line}:{column}: {what}" for line, column, what in find_forbidden(text)]
    return errors


def main(argv: list[str] | None = None) -> int:
    errors = check_files(sys.argv[1:] if argv is None else argv)
    for error in errors:
        print(error)
    if errors:
        print("Tabulation ou caractère de contrôle refusé (voir E-029) : corriger avec l'éditeur, pas un script.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
