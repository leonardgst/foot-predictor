"""Tâches planifiées de la partie 1 (`scripts/taches_planifiees/`), sans rien créer sous Windows."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "taches_planifiees"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("creer_taches", SCRIPTS / "creer_taches.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # les dataclasses cherchent leur module dans sys.modules
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop(spec.name, None)


def test_task_list_matches_the_calendar(module):
    tasks = module.build_tasks()
    assert [(t.name, f"{t.start:%m-%d %H:%M}") for t in tasks] == [
        ("FootPredictor_refresh_2026-10-05", "10-05 08:00"),
        ("FootPredictor_t60_2026-10-09", "10-09 16:00"),
        ("FootPredictor_t60_2026-10-10", "10-10 09:30"),
        ("FootPredictor_t60_2026-10-11", "10-11 09:30"),
        ("FootPredictor_refresh_2026-10-12", "10-12 08:00"),
        ("FootPredictor_t60_2026-10-12", "10-12 16:00"),
        ("FootPredictor_t60_2026-10-16", "10-16 16:00"),
        ("FootPredictor_t60_2026-10-17", "10-17 09:30"),
        ("FootPredictor_t60_2026-10-18", "10-18 09:30"),
    ]
    # Aucune tâche après le dernier week-end avant le gel du 19 octobre (ADR-0005).
    assert max(t.start for t in tasks) < dt.datetime(2026, 10, 19)
    assert all((SCRIPTS / t.script).exists() for t in tasks)


def test_task_xml_has_the_expected_settings(module):
    task = module.build_tasks()[0]
    xml = module.task_xml(task, "PC\\utilisateur", repo_root=Path("C:/foot-predictor"))
    root = ET.fromstring(xml.replace('encoding="UTF-16"', ""))

    def text(path):
        return root.find(path, NS).text

    assert text("t:Triggers/t:TimeTrigger/t:StartBoundary") == "2026-10-05T08:00:00"
    assert text("t:Triggers/t:TimeTrigger/t:EndBoundary") == "2026-10-05T23:00:00"
    assert text("t:Principals/t:Principal/t:LogonType") == "InteractiveToken"  # aucun mot de passe stocké
    for setting, value in (("StartWhenAvailable", "true"), ("WakeToRun", "true"),
                           ("DisallowStartIfOnBatteries", "false"), ("StopIfGoingOnBatteries", "false"),
                           ("MultipleInstancesPolicy", "IgnoreNew")):
        assert text(f"t:Settings/t:{setting}") == value, setting
    assert text("t:Actions/t:Exec/t:Command").replace("\\", "/").endswith("scripts/taches_planifiees/refresh_run.cmd")
    assert text("t:Actions/t:Exec/t:Arguments") == "2026-10-05"


def test_default_run_creates_nothing(module, capsys, monkeypatch):
    monkeypatch.setattr(module, "schtasks", lambda *a: pytest.fail("aucun appel à schtasks attendu"))
    assert module.main([]) == 0
    assert "Simulation : aucune tâche créée" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["refresh_run.cmd", "t60.cmd"])
def test_scripts_cap_their_requests_and_respect_the_lock(name):
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "--max-requests %MAX_REQUESTS%" in text
    assert "--wait-lock" in text
    assert "data\\logs\\" in text  # journal d'exécution, dossier ignoré par Git
    assert "--dry-run" in text
