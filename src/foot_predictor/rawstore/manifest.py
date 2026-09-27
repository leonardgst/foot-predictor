"""Journal des requêtes : `data/raw/_manifest/<source>.jsonl` (rapport G.8).

Une ligne JSON par réponse stockée. Le journal n'est qu'un index : il se
reconstruit entièrement en relisant les fichiers bruts (`rebuild`), à une
exception près, `duration_ms`, qui n'est pas dans l'enveloppe et vaut alors
`null`.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Callable
from pathlib import Path

from foot_predictor.rawstore.store import StoredFile, iter_raw_files, read_envelope, sha256_file

MANIFEST_DIR = "_manifest"

ExtraFields = Callable[[dict], dict]


def manifest_path(raw_dir: Path, source: str) -> Path:
    return Path(raw_dir) / MANIFEST_DIR / f"{source}.jsonl"


def build_entry(
    envelope: dict,
    *,
    source: str,
    file: str,
    sha256: str,
    duration_ms: int | None,
    extra: dict | None = None,
) -> dict:
    """Ligne de journal. `errors` et `results` suivent la convention des API
    api-sports ; ils valent `None` pour une source qui ne les fournit pas."""
    body = envelope.get("body")
    body = body if isinstance(body, dict) else {}
    entry = {
        "timestamp": envelope["fetched_at"],
        "source": source,
        "endpoint": envelope["request"]["endpoint"],
        "params": envelope["request"]["params"],
        "http_status": envelope["http_status"],
        "errors": body.get("errors"),
        "results": body.get("results"),
        "duration_ms": duration_ms,
        "file": file,
        "sha256": sha256,
    }
    entry.update(extra or {})
    return entry


def entry_for_stored(
    envelope: dict,
    stored: StoredFile,
    *,
    source: str,
    duration_ms: int | None,
    extra: dict | None = None,
) -> dict:
    return build_entry(
        envelope,
        source=source,
        file=stored.relative_path,
        sha256=stored.sha256,
        duration_ms=duration_ms,
        extra=extra,
    )


def append_entry(raw_dir: Path, source: str, entry: dict) -> None:
    path = manifest_path(raw_dir, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_entries(raw_dir: Path, source: str) -> list[dict]:
    return read_manifest_file(manifest_path(raw_dir, source))


def read_manifest_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def rebuild(
    raw_dir: Path, source: str, extra_fields: ExtraFields | None = None
) -> tuple[Path, list[dict]]:
    """Reconstruit le journal à partir des fichiers bruts.

    Le résultat est écrit dans un **nouveau** fichier
    `_manifest/<source>.rebuilt-<horodatage>.jsonl` : le journal existant n'est
    jamais écrasé. À toi de comparer, puis de remplacer si besoin.
    """
    raw_dir = Path(raw_dir)
    entries = []
    for path in iter_raw_files(raw_dir, source):
        envelope = read_envelope(path)
        entries.append(
            build_entry(
                envelope,
                source=source,
                file=path.relative_to(raw_dir).as_posix(),
                sha256=sha256_file(path),
                duration_ms=None,
                extra=extra_fields(envelope) if extra_fields else None,
            )
        )
    entries.sort(key=lambda entry: (entry["timestamp"], entry["file"]))

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(raw_dir) / MANIFEST_DIR / f"{source}.rebuilt-{stamp}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "x", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return target, entries
