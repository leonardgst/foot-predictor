"""Tests du contrôle des fins de ligne « \\ » dans les .tex (E-053)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from foot_predictor.outils.latex import check_files, find_lone_backslashes, is_checked, main

REPO = Path(__file__).resolve().parents[2]


def test_lone_backslash_is_found():
    text = "\\begin{cases}\n  1 & a\\\n  2 & b\\\\\n\\end{cases}\n"
    assert find_lone_backslashes(text) == [2]


@pytest.mark.parametrize(
    ("line", "refused"),
    [
        ("1 - \\rho & (a, b) = (1, 1)\\", True),
        ("\\", True),
        ("x \\\\\\", True),  # trois antislashs : un « \\ » suivi d'un antislash seul
        ("1 - \\rho & (a, b) = (1, 1)\\\\", False),
        ("\\\\", False),
        ("\\end{cases}", False),
        ("texte ordinaire", False),
        ("", False),
    ],
)
def test_odd_number_of_trailing_backslashes_is_refused(line, refused):
    assert (find_lone_backslashes(line) == [1]) is refused


def test_crlf_line_endings_are_handled():
    assert find_lone_backslashes("a\\\r\nb\\\\\r\n") == [1]


@pytest.mark.parametrize(
    ("path", "checked"),
    [
        ("docs/latex/mathematiques/main.tex", True),
        ("docs/latex/chapitre.TEX", True),
        ("docs/README.md", False),
        ("src/x.py", False),
    ],
)
def test_is_checked(path, checked):
    assert is_checked(path) is checked


def test_check_files_and_exit_code(tmp_path, capsys):
    bad = tmp_path / "bad.tex"
    bad.write_text("ligne\nfin cassée\\\n", encoding="utf-8")
    good = tmp_path / "good.tex"
    good.write_text("a & b\\\\\nc & d\n", encoding="utf-8")
    ignored = tmp_path / "notes.md"
    ignored.write_text("fin\\\n", encoding="utf-8")

    assert check_files([good, ignored]) == []
    assert main([str(good), str(bad), str(ignored)]) == 1
    assert "bad.tex:2: ligne finie par un seul antislash" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_tracked_tex_files_are_clean():
    """Non-régression de E-053 sur tout le dépôt (tourne aussi en CI)."""
    listed = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    paths = [REPO / name for name in listed.stdout.splitlines() if is_checked(name) and (REPO / name).exists()]
    assert paths, "aucun fichier .tex trouvé"
    assert check_files(paths) == []
