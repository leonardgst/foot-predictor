"""Sauvegarde de `data/raw/` et vérification des sha256 (ADR-0006).

`backup` copie tout le dossier brut (fichiers, journaux, file de travail) vers
une destination vide, puis vérifie la copie avec `verify`. `verify` sert aussi
seul pour le test de restauration du jour du gel.

À lancer quand aucune collecte ne tourne : la file SQLite est copiée telle
quelle.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.rawstore.manifest import MANIFEST_DIR, read_manifest_file
from foot_predictor.rawstore.store import SUFFIX, sha256_file


@dataclass
class VerifyReport:
    verified: int = 0
    mismatched: list[str] = field(default_factory=list)  # sha256 différent
    missing: list[str] = field(default_factory=list)  # dans le journal, absent du disque
    unlisted: list[str] = field(default_factory=list)  # sur le disque, absent du journal

    @property
    def ok(self) -> bool:
        """Les fichiers hors journal sont un avertissement, pas un échec :
        c'est le cas après un plantage entre l'écriture et la ligne de journal."""
        return not self.mismatched and not self.missing


def verify(raw_dir: Path) -> VerifyReport:
    """Vérifie chaque fichier cité par les journaux `_manifest/*.jsonl`."""
    raw_dir = Path(raw_dir)
    report = VerifyReport()
    listed: set[str] = set()
    for manifest in sorted((raw_dir / MANIFEST_DIR).glob("*.jsonl")):
        if ".rebuilt-" in manifest.name:
            continue
        for entry in read_manifest_file(manifest):
            relative = entry["file"]
            listed.add(relative)
            path = raw_dir / relative
            if not path.exists():
                report.missing.append(relative)
            elif sha256_file(path) != entry["sha256"]:
                report.mismatched.append(relative)
            else:
                report.verified += 1

    for path in sorted(raw_dir.rglob(f"*{SUFFIX}")):
        relative = path.relative_to(raw_dir).as_posix()
        if relative not in listed:
            report.unlisted.append(relative)
    return report


def backup(raw_dir: Path, dest: Path) -> VerifyReport:
    """Copie `raw_dir` dans `dest` (qui doit être absent ou vide), puis vérifie."""
    raw_dir, dest = Path(raw_dir), Path(dest)
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Dossier brut introuvable : {raw_dir}")
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"Destination non vide, copie refusée : {dest}")
    if dest.resolve().is_relative_to(raw_dir.resolve()):
        raise ValueError("La destination ne peut pas être à l'intérieur du dossier brut.")
    shutil.copytree(raw_dir, dest, dirs_exist_ok=True)
    return verify(dest)
