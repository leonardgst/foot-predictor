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


def freeze(base, raw, config, *extra):
    return cli.main(
        [
            "--raw-dir",
            str(raw),
            "--config",
            str(config),
            "freeze",
            "--dest",
            str(base / "externe" / "raw"),
            "--restore-to",
            str(base / "restauration" / "raw"),
            "--report-dir",
            str(base / "rapports"),
            "--doc",
            str(base / "docs" / "DATA_FREEZE.md"),
            *extra,
        ]
    )


def mentions_number(text: str, number: int) -> bool:
    """Le nombre figure-t-il tel quel dans le texte (E-036, E-065) ?

    `\\b` ne suffit pas : un point décimal est une limite de mot, et « 0.174 s » contiendrait
    l'identifiant 174 (cas théorique : le brouillon écrit les durées en secondes entières ; la
    vraie cause d'E-036 était le chemin temporaire, voir `leaked_players`). Ici, le nombre ne
    doit toucher ni lettre ni chiffre, ni suivre un séparateur décimal, ni en précéder un suivi
    d'un chiffre : « (174) » et « joueur 174. » le contiennent ; « 0.174 s », « 174,5 »,
    « 1174 » et un sha256 « …e174f… » non.
    """
    return re.search(rf"(?<![\w.,]){number}(?!\w|[.,]\d)", text) is not None


def hold_lock(raw):
    path = lock_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "command": "run",
                "host": socket.gethostname(),
                "started_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )


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
    for section in (
        "## Périmètre",
        "## Volumes",
        "## Contrôle du brut",
        "## Trous connus",
        "## Quota consommé",
        "## Journal et sauvegarde",
        "## À compléter à la main",
    ):
        assert section in doc
    assert "Brouillon généré le" in doc and "sha256 `" in doc
    assert "Matchs terminés avec détail : **5 / 5**" in doc
    assert leaked_players(doc, real, tmp_path) == []


def leaked_players(doc: str, real: list[dict], temp_root) -> list:
    """Noms et identifiants de joueurs présents dans le brouillon, hors chemins du test.

    Le brouillon écrit des chemins absolus (sauvegarde, restauration, résumé `raw_check`),
    ici sous le dossier temporaire de pytest, dont le compteur `pytest-<n>` change à chaque
    exécution : il valait parfois un identifiant de joueur (E-065). On retire donc ce dossier
    (`temp_root`) avant de chercher ; le reste du document est contrôlé tel quel.
    """
    doc = doc.replace(temp_root.as_posix(), "<tmp>")
    players = [e["player"] for item in real for team in item["players"] for e in team["players"]]
    names = sorted({p["name"] for p in players if p["name"] in doc})
    ids = sorted({p["id"] for p in players if mentions_number(doc, p["id"])})
    return names + ids


def test_player_ids_in_temporary_paths_are_not_leaks(tmp_path, setup, real, capsys):
    """E-065 : un dossier temporaire `…/pytest-531` n'est pas un identifiant de joueur publié.

    `base` joue le dossier temporaire du test, dont le nom contient l'identifiant 531 d'un joueur
    de la fixture (nom court : limite de 260 caractères des chemins sous Windows).
    """
    raw, config = setup
    base = tmp_path / "531"
    assert 531 in {e["player"]["id"] for item in real for team in item["players"] for e in team["players"]}

    assert freeze(base, raw, config) == 0, capsys.readouterr().err
    doc = (base / "docs" / "DATA_FREEZE.md").read_text(encoding="utf-8")
    assert mentions_number(doc, 531)  # le cas est bien exercé : le chemin contient l'identifiant
    assert leaked_players(doc, real, base) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("raw_check 0.174 s", False),  # la durée qui faisait échouer le test (E-036)
        ("174,5 Mo", False),
        ("1174 fichiers", False),
        ("sha256 `e174f0`", False),
        ("joueur 174.", True),
        ("(174)", True),
        ("174 : nom", True),
    ],
)
def test_mentions_number_ignores_decimals_longer_numbers_and_hashes(text, expected):
    assert mentions_number(text, 174) is expected


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
