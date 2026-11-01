"""Planification du live (ADR-0053) : trois passages par semaine dans le Planificateur de tâches Windows.

    uv run python -m foot_predictor.planification run mardi|vendredi|samedi [--force]
    uv run python -m foot_predictor.planification install [--apply]      # sans --apply : affiche le plan
    uv run python -m foot_predictor.planification uninstall
    uv run python -m foot_predictor.planification status

Un passage enchaîne des étapes dont les commandes sont **écrites en dur ici** (liste fermée) :

- *collecte* : `collect.football_data.live fixtures --max-requests 1`, puis `season --season <saison> --max-requests 10` ;
- *tracé* : `inference live --days 7 --save` (idempotent ; seulement avant le coup d'envoi) ;
- *relevé* : `inference prospective`.

Autorisation durable bornée (ADR-0053) : football-data seulement, aucune requête API-FOOTBALL, aucun `load`,
tout plafonné par `--max-requests`. Le lanceur refuse toute autre commande (`check_command`), s'arrête si
`data/planification/STOP` existe, ne tourne pas après le 30 juin 2027, et ignore un passage manqué qui ne
tombe plus le jour prévu (sauf `--force`). Journal : `data/planification/passages.log` (ignoré par Git).

Les tâches sont décrites en XML, comme celles de la partie 1 (`scripts/taches_planifiees/creer_taches.py`),
car `schtasks /Create` ne règle pas `StartWhenAvailable` ni `WakeToRun`. Elles tournent sous la session de
l'utilisateur, sans mot de passe stocké.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "data" / "planification"
LOG_FILE = LOG_DIR / "passages.log"
STOP_FILE = LOG_DIR / "STOP"
PREFIX = "FootPredictor_live_"
AUTHORIZED_UNTIL = dt.date(2027, 6, 30)
"""Fin de l'autorisation (ADR-0053) : la saison 2026-27 ; la renouveler demande une nouvelle ADR."""
STEP_TIMEOUT_SECONDS = 30 * 60

FIXTURES_MODULE = "foot_predictor.collect.football_data.live"
INFERENCE_MODULE = "foot_predictor.inference"
REQUEST_CAPS = {"fixtures": 1, "season": 10}
"""Plafond de requêtes de chaque commande de collecte : 11 par passage de collecte, 22 par semaine au plus."""
ALLOWED = {
    (FIXTURES_MODULE, "fixtures"),
    (FIXTURES_MODULE, "season"),
    (INFERENCE_MODULE, "live"),
    (INFERENCE_MODULE, "prospective"),
}
FORBIDDEN_PARTS = ("api_football", "ingestion", "sealed")
FORBIDDEN_TOKENS = ("load", "download")


class CommandRefused(ValueError):
    """Une commande hors de la liste fermée de l'ADR-0053."""


@dataclass(frozen=True)
class Passage:
    name: str
    weekday: int  # lundi = 0
    day_code: str  # code du Planificateur de tâches
    time: str  # heure locale (Paris), HH:MM
    steps: tuple[str, ...]
    description: str


PASSAGES = {
    "mardi": Passage(
        "mardi", 1, "Tuesday", "18:00", ("collecte", "tracé", "relevé"),
        "foot-predictor : résultats du week-end et prochains matchs (football-data), tracé du live, relevé du journal",
    ),
    "vendredi": Passage(
        "vendredi", 4, "Friday", "17:00", ("collecte", "tracé"),
        "foot-predictor : prochains matchs publiés l'après-midi (football-data) et tracé avant les matchs du soir",
    ),
    "samedi": Passage(
        "samedi", 5, "Saturday", "08:00", ("tracé",),
        "foot-predictor : nouveau tracé du live avant les matchs du samedi, sans réseau",
    ),
}  # fmt: skip


def season_year(day: dt.date) -> int:
    """Année de début de la saison d'un jour : une saison commence le 1er juillet."""
    return day.year if day.month >= 7 else day.year - 1


def step_commands(step: str, today: dt.date) -> list[tuple[str, ...]]:
    """Commandes d'une étape, sans `python` : `("-m", module, sous-commande, options...)`."""
    if step == "collecte":
        return [
            ("-m", FIXTURES_MODULE, "fixtures", "--max-requests", str(REQUEST_CAPS["fixtures"])),
            ("-m", FIXTURES_MODULE, "season", "--season", str(season_year(today)),
             "--max-requests", str(REQUEST_CAPS["season"])),
        ]  # fmt: skip
    if step == "tracé":
        return [("-m", INFERENCE_MODULE, "live", "--days", "7", "--save")]
    if step == "relevé":
        return [("-m", INFERENCE_MODULE, "prospective")]
    raise CommandRefused(f"Étape inconnue : {step}")


def check_command(command: Sequence[str]) -> None:
    """Refuse toute commande hors de la liste fermée, ou une collecte sans plafond valide (ADR-0053)."""
    if len(command) < 3 or command[0] != "-m":
        raise CommandRefused(f"Commande refusée (forme inattendue) : {list(command)}")
    module, sub = command[1], command[2]
    if (module, sub) not in ALLOWED:
        raise CommandRefused(f"Commande refusée (hors de la liste de l'ADR-0053) : {module} {sub}")
    for argument in command:
        if argument in FORBIDDEN_TOKENS or any(part in argument for part in FORBIDDEN_PARTS):
            raise CommandRefused(f"Commande refusée (mot interdit) : {argument}")
    if module == FIXTURES_MODULE:
        if "--max-requests" not in command:
            raise CommandRefused("Collecte refusée : --max-requests est obligatoire")
        cap = int(command[command.index("--max-requests") + 1])
        if not 1 <= cap <= REQUEST_CAPS[sub]:
            raise CommandRefused(f"Collecte refusée : --max-requests {cap} hors de 1 à {REQUEST_CAPS[sub]}")


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def uv_executable() -> str:
    found = shutil.which("uv")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "uv.exe"
    return str(candidate) if candidate.exists() else "uv"


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess:
    """Lance une commande autorisée avec `uv run`, depuis ce dépôt, sortie capturée."""
    check_command(command)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [uv_executable(), "run", "--directory", str(REPO_ROOT), "python", *command],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=STEP_TIMEOUT_SECONDS, check=False,
    )  # fmt: skip


def current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def log_line(text: str, log_file: Path = LOG_FILE, now: dt.datetime | None = None) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    stamp = (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    with log_file.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"[{stamp}] {text}\n")


def tail(text: str, lines: int = 6) -> str:
    kept = [line for line in (text or "").splitlines() if line.strip()][-lines:]
    return " | ".join(kept)[:1500]


def run_passage(
    name: str,
    *,
    now: dt.datetime | None = None,
    runner: Runner = run_command,
    force: bool = False,
    log_file: Path = LOG_FILE,
    stop_file: Path = STOP_FILE,
    commit: str | None = None,
) -> int:
    """Un passage : 0 si tout est bon (ou ignoré par règle), 1 si une étape a échoué, 4 si l'autorisation est tombée."""
    passage = PASSAGES[name]
    now = now or dt.datetime.now()
    today = now.date()
    head = f"passage {name} (commit {commit or current_commit()})"

    def log(text: str) -> None:
        log_line(f"{head} : {text}", log_file, now)

    if today > AUTHORIZED_UNTIL:
        log(f"refusé : autorisation échue le {AUTHORIZED_UNTIL.isoformat()} (ADR-0053)")
        return 4
    if stop_file.exists():
        log("suspendu : fichier STOP présent")
        return 0
    if not force and now.weekday() != passage.weekday:
        log(f"ignoré : passage manqué, on est {now:%A %d/%m} et il était prévu le jour {passage.day_code}")
        return 0
    failed: set[str] = set()
    for step in passage.steps:
        if step == "relevé" and "tracé" in failed:
            log(f"étape {step} sautée : le tracé a échoué")
            continue
        for command in step_commands(step, today):
            label = f"{step} {command[2]}"
            try:
                done = runner(command)
            except Exception as error:  # noqa: BLE001 : un échec est journalisé, il n'arrête pas les autres étapes
                failed.add(step)
                log(f"étape {label} : ERREUR {type(error).__name__} : {str(error)[:300]}")
                continue
            if done.returncode == 0:
                log(f"étape {label} : ok ({tail(done.stdout, 1)})")
            else:
                failed.add(step)
                log(f"étape {label} : ÉCHEC code {done.returncode} ({tail(done.stderr or done.stdout)})")
    log("terminé" + (f", étapes en échec : {', '.join(sorted(failed))}" if failed else ", tout est bon"))
    return 1 if failed else 0


# --------------------------------------------------------------------------------- Planificateur Windows


def task_name(passage: Passage) -> str:
    return f"{PREFIX}{passage.name}"


def next_occurrence(passage: Passage, today: dt.date) -> dt.datetime:
    """Première date d'application : le prochain jour de la semaine voulu, à l'heure voulue."""
    ahead = (passage.weekday - today.weekday()) % 7
    hour, minute = (int(part) for part in passage.time.split(":"))
    return dt.datetime.combine(today + dt.timedelta(days=ahead), dt.time(hour, minute))


def task_xml(passage: Passage, user: str, today: dt.date, repo_root: Path = REPO_ROOT, uv: str | None = None) -> str:
    start = next_occurrence(passage, today)
    arguments = f'run --directory "{repo_root}" python -m foot_predictor.planification run {passage.name}'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{escape(passage.description)} (ADR-0053)</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <EndBoundary>{AUTHORIZED_UNTIL.isoformat()}T23:00:00</EndBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek><{passage.day_code} /></DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
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
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(uv or uv_executable())}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(str(repo_root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def current_user() -> str:
    domain, user = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
    if not user:
        raise SystemExit("USERNAME inconnu : lancer cette commande depuis la session Windows de l'utilisateur.")
    return f"{domain}\\{user}" if domain else user


def schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, check=False)


def install(
    *, apply: bool, today: dt.date | None = None, user: str | None = None, run: Callable[..., object] = schtasks
) -> list[str]:
    """Crée ou remplace les trois tâches (`apply`), sinon décrit seulement le plan. Renvoie les lignes affichées."""
    today = today or dt.date.today()
    lines = [
        f"{task_name(p):<30} {p.day_code:<9} {p.time}  première le {next_occurrence(p, today):%Y-%m-%d}  "
        f"étapes : {', '.join(p.steps)}"
        for p in PASSAGES.values()
    ]
    if not apply:
        return [*lines, "Simulation : aucune tâche créée (--apply pour créer ou remplacer)."]
    user = user or current_user()
    with tempfile.TemporaryDirectory(prefix="fp_planification_") as tmp:
        for passage in PASSAGES.values():
            path = Path(tmp) / f"{task_name(passage)}.xml"
            path.write_text(task_xml(passage, user, today), encoding="utf-16")  # schtasks exige de l'UTF-16
            done = run("/Create", "/TN", task_name(passage), "/XML", str(path), "/F")
            lines.append(f"{task_name(passage)} : {'créée' if done.returncode == 0 else 'ÉCHEC ' + tail(done.stderr)}")
    return lines


def uninstall(*, run: Callable[..., object] = schtasks) -> list[str]:
    lines = []
    for passage in PASSAGES.values():
        done = run("/Delete", "/TN", task_name(passage), "/F")
        lines.append(f"{task_name(passage)} : {'supprimée' if done.returncode == 0 else 'absente ou ÉCHEC'}")
    return lines


def status(*, run: Callable[..., object] = schtasks) -> list[str]:
    lines = []
    for passage in PASSAGES.values():
        done = run("/Query", "/TN", task_name(passage), "/FO", "LIST")
        lines.append(f"{task_name(passage)} : {'présente' if done.returncode == 0 else 'absente'}")
    lines.append(f"Interrupteur : {'STOP présent (passages suspendus)' if STOP_FILE.exists() else 'aucun'}.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.planification", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="lance un passage (collecte, tracé, relevé selon le jour)")
    run.add_argument("passage", choices=sorted(PASSAGES))
    run.add_argument("--force", action="store_true", help="lance même si ce n'est pas le jour prévu")
    create = sub.add_parser("install", help="crée ou remplace les trois tâches du Planificateur")
    create.add_argument("--apply", action="store_true", help="crée réellement ; sans cette option, affiche le plan")
    sub.add_parser("uninstall", help="supprime les trois tâches")
    sub.add_parser("status", help="dit quelles tâches existent")
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_passage(args.passage, force=args.force)
    if sys.platform != "win32" and args.command != "install":
        raise SystemExit("Planificateur de tâches : Windows uniquement.")
    lines = {"install": lambda: install(apply=args.apply), "uninstall": uninstall, "status": status}[args.command]()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
