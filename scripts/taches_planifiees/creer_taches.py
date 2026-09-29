"""Crée, liste ou supprime les tâches planifiées Windows de la collecte (partie 1).

    uv run python scripts/taches_planifiees/creer_taches.py            # affiche le plan, ne crée rien
    uv run python scripts/taches_planifiees/creer_taches.py --apply    # crée (ou remplace) les tâches
    uv run python scripts/taches_planifiees/creer_taches.py --delete   # supprime les tâches de la liste

Chaque tâche est décrite en XML (format du Planificateur de tâches) plutôt
qu'avec les options de `schtasks /Create`, qui ne savent pas régler :

- `StartWhenAvailable` : une tâche manquée (portable éteint à l'heure dite)
  démarre dès que possible, le jour même (voir `EndBoundary`) ;
- `WakeToRun` : sortir le portable de veille pour démarrer la tâche ;
- `DisallowStartIfOnBatteries` et `StopIfGoingOnBatteries` à false :
  la tâche tourne aussi sur batterie ;
- `EndBoundary` à 23:00 le même jour : une tâche manquée ne démarre jamais
  le lendemain ;
- `ExecutionTimeLimit` de 16 heures : une journée T-60 complète.

`LogonType = InteractiveToken` : la tâche tourne sous la session ouverte de
l'utilisateur, sans mot de passe stocké. Elle ne démarre donc que si la
session est ouverte (verrouillée, cela suffit).

Aucune requête API ici : les scripts `.cmd` lancés par les tâches portent
leurs plafonds (`--max-requests`).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parents[1]
PREFIX = "FootPredictor_"


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    start: dt.datetime  # heure locale (Paris)
    script: str
    argument: str
    description: str


def build_tasks() -> list[ScheduledTask]:
    """Tâches de la partie 1 (ADR-0005 et décisions du 2026-09-29).

    - refresh puis run : lundis 5 et 12 octobre, 08:00 ;
    - T-60 : journées du top 5 avant le gel. Samedi et dimanche à 09:30
      (premier coup d'envoi vers 10:30 UTC, soit une fenêtre à 11:50 à Paris) ;
      vendredi et lundi à 16:00 (matchs du soir).
    """
    tasks = [
        ScheduledTask(f"{PREFIX}refresh_{day}", dt.datetime.fromisoformat(f"{day}T08:00"), "refresh_run.cmd", day,
                      "foot-predictor : refresh de la saison 2026 puis run plafonné (250 requêtes)")
        for day in ("2026-10-05", "2026-10-12")
    ]
    for day, hour in (("2026-10-09", "16:00"), ("2026-10-10", "09:30"), ("2026-10-11", "09:30"),
                      ("2026-10-12", "16:00"), ("2026-10-16", "16:00"), ("2026-10-17", "09:30"),
                      ("2026-10-18", "09:30")):
        tasks.append(ScheduledTask(f"{PREFIX}t60_{day}", dt.datetime.fromisoformat(f"{day}T{hour}"), "t60.cmd", day,
                                   "foot-predictor : journal T-60 du top 5 (80 requêtes au plus)"))
    return sorted(tasks, key=lambda t: t.start)


def task_xml(task: ScheduledTask, user: str, repo_root: Path = REPO_ROOT) -> str:
    end = task.start.replace(hour=23, minute=0)
    command = repo_root / "scripts" / "taches_planifiees" / task.script
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{escape(task.description)}</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{task.start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <EndBoundary>{end:%Y-%m-%dT%H:%M:%S}</EndBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT16H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(command))}</Command>
      <Arguments>{escape(task.argument)}</Arguments>
      <WorkingDirectory>{escape(str(repo_root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def current_user() -> str:
    domain, user = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
    if not user:
        raise SystemExit("USERNAME inconnu : lancer ce script depuis la session Windows de l'utilisateur.")
    return f"{domain}\\{user}" if domain else user


def schtasks(*args: str) -> int:
    return subprocess.run(["schtasks", *args], check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="créer ou remplacer les tâches")
    group.add_argument("--delete", action="store_true", help="supprimer les tâches de la liste")
    args = parser.parse_args(argv)

    tasks = build_tasks()
    for task in tasks:
        print(f"{task.name:<32} {task.start:%Y-%m-%d %H:%M}  {task.script} {task.argument}")
    if not (args.apply or args.delete):
        print("\nSimulation : aucune tâche créée (--apply pour créer, --delete pour supprimer).")
        return 0
    if sys.platform != "win32":
        raise SystemExit("Tâches planifiées : Windows uniquement.")

    failures = 0
    if args.delete:
        for task in tasks:
            failures += schtasks("/Delete", "/TN", task.name, "/F") != 0
        return 1 if failures else 0

    user = current_user()
    with tempfile.TemporaryDirectory(prefix="fp_taches_") as tmp:
        for task in tasks:
            path = Path(tmp) / f"{task.name}.xml"
            path.write_text(task_xml(task, user), encoding="utf-16")  # schtasks exige de l'UTF-16
            failures += schtasks("/Create", "/TN", task.name, "/XML", str(path), "/F") != 0
    print("\nVérifier : schtasks /Query /FO TABLE /TN <nom>  (ou le Planificateur de tâches, dossier racine).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
