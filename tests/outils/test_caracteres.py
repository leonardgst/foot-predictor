"""Tests du contrôle des tabulations et caractères de contrôle (E-029)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from foot_predictor.outils.caracteres import check_files, find_forbidden, is_checked, main

REPO = Path(__file__).resolve().parents[2]


def test_tab_is_found_with_position():
    assert find_forbidden('ok\ncmd //c "scripts\taches"\n') == [(2, 17, "tabulation")]


def test_crlf_and_newlines_are_allowed():
    assert find_forbidden("@echo off\r\ngoto fin\r\n") == []


def test_other_control_characters_are_found():
    found = find_forbidden("a\x00b\x1bc\x7f")
    assert [what for _, _, what in found] == ["caractère de contrôle U+0000", "caractère de contrôle U+001B", "DEL"]


@pytest.mark.parametrize(
    ("path", "checked"),
    [
        ("docs/README.md", True),
        ("src/x.py", True),
        ("config/a.yaml", True),
        ("scripts/t.cmd", True),
        ("docs/archives/ancien.md", False),
        ("data.csv", False),
        ("uv.lock", False),
    ],
)
def test_is_checked(path, checked):
    assert is_checked(path) is checked


def test_check_files_and_exit_code(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_text("ligne\tavec tabulation\n", encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text("x = '\\t'\n", encoding="utf-8")  # « \t » écrit en toutes lettres : autorisé
    ignored = tmp_path / "data.csv"
    ignored.write_text("a\tb\n", encoding="utf-8")

    assert check_files([good, ignored]) == []
    assert main([str(good), str(bad), str(ignored)]) == 1
    assert "bad.md:1:6: tabulation" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_tracked_files_are_clean():
    """Non-régression de E-029 sur tout le dépôt (tourne aussi en CI)."""
    listed = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    paths = [REPO / name for name in listed.stdout.splitlines() if is_checked(name) and (REPO / name).exists()]
    assert paths, "aucun fichier contrôlé trouvé"
    assert check_files(paths) == []
