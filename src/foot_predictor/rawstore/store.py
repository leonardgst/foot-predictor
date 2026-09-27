"""Écriture et lecture des fichiers bruts (ADR-0003, rapport G.6 et G.7).

Chaque fichier est autoportant : une enveloppe
`{request, fetched_at, http_status, headers_quota, body}` compressée en gzip,
où `body` est la réponse de la source intacte.

Nom de fichier : `<stem>__<AAAAMMJJTHHMMSSffffffZ>.json.gz`. L'horodatage est
présent dès la première version : une recollecte crée simplement un nouveau
fichier à côté, et le chargeur prend la version la plus récente (le tri
alphabétique des noms suit l'ordre chronologique).
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

SUFFIX = ".json.gz"
VERSION_SEPARATOR = "__"
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
TMP_SUFFIX = ".tmp"


class RawFileExistsError(FileExistsError):
    """Le fichier cible existe déjà : on n'écrase jamais un brut."""


@dataclass(frozen=True)
class StoredFile:
    path: Path
    relative_path: str  # chemin relatif au dossier brut, séparateurs « / »
    sha256: str


def build_envelope(
    *,
    endpoint: str,
    params: dict,
    fetched_at: dt.datetime,
    http_status: int,
    headers_quota: dict,
    body: object,
) -> dict:
    return {
        "request": {"endpoint": endpoint, "params": params},
        "fetched_at": fetched_at.isoformat(),
        "http_status": http_status,
        "headers_quota": headers_quota,
        "body": body,
    }


def versioned_name(stem: str, fetched_at: dt.datetime) -> str:
    stamp = fetched_at.astimezone(dt.timezone.utc).strftime(TIMESTAMP_FORMAT)
    return f"{stem}{VERSION_SEPARATOR}{stamp}{SUFFIX}"


def encode_envelope(envelope: dict) -> bytes:
    """JSON puis gzip avec `mtime=0` : le même contenu donne toujours les
    mêmes octets, donc le même sha256 (l'en-tête gzip contient sinon la date)."""
    payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return gzip.compress(payload, mtime=0)


def write_envelope(
    raw_dir: Path, relative_dir: str, stem: str, envelope: dict, fetched_at: dt.datetime
) -> StoredFile:
    """Écrit l'enveloppe de façon atomique, sans jamais écraser.

    Étapes : écriture complète dans `<nom>.tmp`, `fsync` (les octets sont sur
    le disque), puis renommage. Un plantage pendant l'écriture laisse au pire
    un `.tmp` orphelin, jamais un `.json.gz` tronqué.
    """
    target_dir = Path(raw_dir) / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    final = target_dir / versioned_name(stem, fetched_at)
    if final.exists():
        raise RawFileExistsError(f"Fichier brut déjà présent, écriture refusée : {final}")

    data = encode_envelope(envelope)
    tmp = final.with_name(final.name + TMP_SUFFIX)
    with open(tmp, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        # Seconde vérification juste avant le renommage : sous Linux,
        # os.rename écraserait silencieusement un fichier existant (sous
        # Windows, il lève FileExistsError).
        if final.exists():
            raise RawFileExistsError(f"Fichier brut déjà présent, écriture refusée : {final}")
        os.rename(tmp, final)
    finally:
        if tmp.exists():
            tmp.unlink()

    return StoredFile(
        path=final,
        relative_path=final.relative_to(raw_dir).as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def read_envelope(path: Path) -> dict:
    with gzip.open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_version(raw_dir: Path, relative_dir: str, stem: str) -> Path | None:
    """Version la plus récente d'un fichier brut, ou None s'il n'existe pas."""
    directory = Path(raw_dir) / relative_dir
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob(f"{stem}{VERSION_SEPARATOR}*{SUFFIX}"))
    return candidates[-1] if candidates else None


def iter_raw_files(raw_dir: Path, source: str) -> list[Path]:
    """Tous les fichiers bruts d'une source (les `.tmp` orphelins sont ignorés)."""
    source_dir = Path(raw_dir) / source
    if not source_dir.is_dir():
        return []
    return sorted(source_dir.rglob(f"*{SUFFIX}"))
