"""Fichiers bruts stockés octet pour octet (sources qui ne sont pas du JSON).

`rawstore.store` écrit des enveloppes JSON compressées (`.json.gz`). Pour
football-data, l'ADR-0003 demande le CSV **tel que téléchargé** : ses octets
exacts (encodage et BOM compris), pas une chaîne réencodée dans du JSON. Ce
module ajoute cette capacité **à côté** de `rawstore/`, sans le modifier
(règles du gel, partie 2), et en reprend les conventions :

- nom versionné `<stem>__<AAAAMMJJTHHMMSSffffffZ><suffixe>` : une nouvelle
  version s'ajoute à côté, rien n'est jamais écrasé ;
- écriture atomique (`.tmp`, `fsync`, renommage) ;
- une ligne de journal `_manifest/<source>.jsonl` par fichier stocké, avec
  `file` et `sha256` : `backup`, `verify` et `raw_check` vérifient ces fichiers
  comme les autres.

Les métadonnées de la requête (URL, date, statut HTTP, taille) vont dans la
ligne de journal : le fichier, lui, reste identique à la réponse.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path

from foot_predictor.rawstore.store import (
    TIMESTAMP_FORMAT,
    TMP_SUFFIX,
    VERSION_SEPARATOR,
    RawFileExistsError,
    StoredFile,
)


def versioned_name(stem: str, suffix: str, fetched_at: dt.datetime) -> str:
    stamp = fetched_at.astimezone(dt.UTC).strftime(TIMESTAMP_FORMAT)
    return f"{stem}{VERSION_SEPARATOR}{stamp}{suffix}"


def write_bytes(
    raw_dir: Path, relative_dir: str, stem: str, suffix: str, data: bytes, fetched_at: dt.datetime
) -> StoredFile:
    """Écrit `data` tel quel, de façon atomique, sans jamais écraser un fichier existant."""
    raw_dir = Path(raw_dir)
    target_dir = raw_dir / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    final = target_dir / versioned_name(stem, suffix, fetched_at)
    if final.exists():
        raise RawFileExistsError(f"Fichier brut déjà présent, écriture refusée : {final}")
    tmp = final.with_name(final.name + TMP_SUFFIX)
    with open(tmp, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if final.exists():  # sous Linux, os.rename écraserait sans rien dire
            raise RawFileExistsError(f"Fichier brut déjà présent, écriture refusée : {final}")
        os.rename(tmp, final)
    finally:
        if tmp.exists():
            tmp.unlink()
    return StoredFile(
        path=final, relative_path=final.relative_to(raw_dir).as_posix(), sha256=hashlib.sha256(data).hexdigest()
    )


def versions(raw_dir: Path, relative_dir: str, stem: str, suffix: str) -> list[Path]:
    """Toutes les versions d'un fichier, de la plus ancienne à la plus récente
    (l'horodatage du nom suit l'ordre alphabétique)."""
    directory = Path(raw_dir) / relative_dir
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{stem}{VERSION_SEPARATOR}*{suffix}"))


def latest(raw_dir: Path, relative_dir: str, stem: str, suffix: str) -> Path | None:
    found = versions(raw_dir, relative_dir, stem, suffix)
    return found[-1] if found else None
