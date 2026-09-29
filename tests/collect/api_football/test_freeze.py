"""Commande `freeze` (gel des données) et sauvegarde sous verrou, sans aucun appel réseau."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket

import pytest
import yaml

from foot_predictor.collect.api_football import cli
from foot_predictor.rawstore.backup import backup
from foot_predictor.rawstore.lock import lock_path
from tests.quality.test_raw_check import CONFIG, build_clean, list_item, listing_of, load_real_fixtures, snapshot


@pytest.fixture
def real():
    return load_real_fixtures()


@pytest.fixture
def setup(tmp_path, real):
    raw = tmp_path / "raw"
    build_clean(raw, real).queue.close()
    config = tmp_path / "collecte.yaml"
    config.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return raw, config


def freeze(tmp_path, raw, config, *extra):
    return cli.main(["--raw-dir", str(raw), "--config", str(config), "freeze",
                     "--dest", str(tmp_path / "externe" / "raw"), "--restore-to", str(tmp_path / "restauration" / "raw"),
                     "--report-dir", str(tmp_path / "rapports"), "--doc", str(tmp_path / "docs" / "DATA_FREEZE.md"),
                     *extra])


def hold_lock(raw):
    path = lock_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": os.getpid(), "command": "run", "host": socket.gethostname(),
                                "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}), encoding="utf-8")


def test_freeze_checks_saves_restores_and_drafts_data_freeze(tmp_path, setup, real, capsys):
    raw, config = setup
    before = snapshot(raw)

    code = freeze(tmp_path, raw, config)

    assert code == 0, capsys.readouterr().err
    assert snapshot(raw) == before  # rien d'écrit dans le brut ; verrou retiré
    assert not lock_path(raw).exists()
    saved, restored = tmp_path / "externe" / "raw", tmp_path / "restauration" / "raw"
    files = {p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    assert {p.relative_to(saved).as_posix() for p in saved.rglob("*") if p.is_file()} == files
    assert {p.relative_to(restored).as_posix() for p in restored.rglob("*") if p.is_file()} == files
    assert list((tmp_path / "rapports").glob("raw_check_tous_*.md"))
    out = capsys.readouterr().out
    assert "Sauvegarde : " in out and "restauration" in out and "Durée totale" in out

    doc = (tmp_path / "docs" / "DATA_FREEZE.md").read_text(encoding="utf-8")
    for section in ("## Périmètre", "## Volumes", "## Contrôle du brut", "## Trous connus", "## Quota consommé",
                    "## Journal et sauvegarde", "## À compléter à la main"):
        assert section in doc
    assert "Brouillon généré le" in doc and "sha256 `" in doc
    assert "Matchs terminés avec détail : **5 / 5**" in doc
    # Aucun nom ni identifiant de joueur dans le document versionné.
    names = {e["player"]["name"] for item in real for team in item["players"] for e in team["players"]}
    assert [n for n in names if n in doc] == []
    ids = {e["player"]["id"] for item in real for team in item["players"] for e in team["players"]}
    assert [i for i in ids if re.search(rf"\b{i}\b", doc)] == []


def test_blocking_verdict_stops_the_freeze_before_any_copy(tmp_path, real, capsys):
    raw, config = tmp_path / "raw", tmp_path / "collecte.yaml"
    config.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    builder = build_clean(raw, real)  # même horloge : la nouvelle liste est bien la plus récente
    builder.fixtures_list(39, listing_of(real) + [list_item(999003, 33, 47)])  # match terminé sans détail
    builder.queue.close()

    assert freeze(tmp_path, raw, config) == 1
    assert "BLOQUANT" in capsys.readouterr().err
    assert not (tmp_path / "externe").exists()
    assert not lock_path(raw).exists()
    assert freeze(tmp_path, raw, config, "--allow-blocking") == 0


def test_freeze_refuses_to_start_while_a_collection_runs(tmp_path, setup, capsys):
    raw, config = setup
    hold_lock(raw)
    assert freeze(tmp_path, raw, config) == 3
    assert "occupé" in capsys.readouterr().err
    assert not (tmp_path / "externe").exists()


def test_backup_command_refuses_a_held_lock_and_never_copies_it(tmp_path, setup, capsys):
    raw, config = setup
    hold_lock(raw)
    code = cli.main(["--raw-dir", str(raw), "--config", str(config), "backup", "--dest", str(tmp_path / "copie")])
    assert code == 2 and "Copie refusée" in capsys.readouterr().err

    report = backup(raw, tmp_path / "copie2")  # appel direct (utilisé par freeze, verrou déjà pris)
    assert report.ok
    assert not (tmp_path / "copie2" / "_lock").exists()
