"""Planification du live (ADR-0053) : liste fermée, plafonds, passages, tâches XML. Rien n'est créé, aucun réseau."""

from __future__ import annotations

import datetime as dt
import subprocess
import xml.etree.ElementTree as ET

import pytest

from foot_predictor import planification as pl

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
TUESDAY = dt.datetime(2026, 11, 3, 18, 0)  # un mardi
FRIDAY = dt.datetime(2026, 11, 6, 17, 0)
SATURDAY = dt.datetime(2026, 11, 7, 8, 0)


def done(code: int = 0, out: str = "ok", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout=out, stderr=err)


class Recorder:
    """Lanceur simulé : garde les commandes, échoue sur demande."""

    def __init__(self, fail: tuple[str, ...] = (), raises: tuple[str, ...] = ()):
        self.commands: list[tuple[str, ...]] = []
        self.fail, self.raises = fail, raises

    def __call__(self, command):
        pl.check_command(command)  # le vrai lanceur le fait aussi
        self.commands.append(tuple(command))
        if command[2] in self.raises:
            raise TimeoutError("trop long")
        return done(1, "", "boum") if command[2] in self.fail else done()


def passage(name, tmp_path, runner, now, **kwargs):
    return pl.run_passage(
        name, now=now, runner=runner, log_file=tmp_path / "passages.log", stop_file=tmp_path / "STOP", commit="abc123",
        **kwargs,
    )  # fmt: skip


def test_the_three_passages_match_the_adr():
    assert {n: (p.day_code, p.time, p.steps) for n, p in pl.PASSAGES.items()} == {
        "mardi": ("Tuesday", "18:00", ("collecte", "tracé", "relevé")),
        "vendredi": ("Friday", "17:00", ("collecte", "tracé")),
        "samedi": ("Saturday", "08:00", ("tracé",)),
    }
    assert [p.weekday for p in pl.PASSAGES.values()] == [1, 4, 5]


def test_a_tuesday_runs_collection_then_trace_then_report_in_order(tmp_path):
    runner = Recorder()
    assert passage("mardi", tmp_path, runner, TUESDAY) == 0
    assert [c[2] for c in runner.commands] == ["fixtures", "season", "live", "prospective"]
    season = next(c for c in runner.commands if c[2] == "season")
    assert season[season.index("--season") + 1] == "2026"
    assert ("-m", pl.INFERENCE_MODULE, "live", "--days", "7", "--save") in runner.commands
    log = (tmp_path / "passages.log").read_text(encoding="utf-8")
    assert "commit abc123" in log and "terminé, tout est bon" in log


def test_friday_has_no_report_and_saturday_does_not_touch_the_network(tmp_path):
    friday, saturday = Recorder(), Recorder()
    passage("vendredi", tmp_path, friday, FRIDAY)
    passage("samedi", tmp_path, saturday, SATURDAY)
    assert [c[2] for c in friday.commands] == ["fixtures", "season", "live"]
    assert [c[2] for c in saturday.commands] == ["live"]
    assert not any(pl.FIXTURES_MODULE in c for c in saturday.commands)


def test_a_failed_collection_does_not_stop_the_trace_but_a_failed_trace_skips_the_report(tmp_path):
    collect_fails = Recorder(fail=("season",))
    assert passage("mardi", tmp_path, collect_fails, TUESDAY) == 1
    assert [c[2] for c in collect_fails.commands] == ["fixtures", "season", "live", "prospective"]
    trace_fails = Recorder(fail=("live",))
    assert passage("mardi", tmp_path, trace_fails, TUESDAY) == 1
    assert [c[2] for c in trace_fails.commands] == ["fixtures", "season", "live"]  # pas de relevé
    log = (tmp_path / "passages.log").read_text(encoding="utf-8")
    assert "ÉCHEC code 1 (boum)" in log and "étape relevé sautée" in log


def test_an_exception_in_a_step_is_logged_and_the_next_steps_still_run(tmp_path):
    runner = Recorder(raises=("fixtures",))
    assert passage("vendredi", tmp_path, runner, FRIDAY) == 1
    assert [c[2] for c in runner.commands] == ["fixtures", "season", "live"]  # la commande en erreur est tentée
    assert "ERREUR TimeoutError" in (tmp_path / "passages.log").read_text(encoding="utf-8")


def test_the_stop_file_suspends_everything(tmp_path):
    (tmp_path / "STOP").write_text("", encoding="utf-8")
    runner = Recorder()
    assert passage("mardi", tmp_path, runner, TUESDAY) == 0
    assert runner.commands == []
    assert "suspendu" in (tmp_path / "passages.log").read_text(encoding="utf-8")


def test_a_missed_passage_on_another_day_is_ignored_unless_forced(tmp_path):
    runner = Recorder()
    assert passage("mardi", tmp_path, runner, TUESDAY + dt.timedelta(days=1)) == 0  # mercredi
    assert runner.commands == []
    assert "ignoré" in (tmp_path / "passages.log").read_text(encoding="utf-8")
    assert passage("mardi", tmp_path, runner, TUESDAY + dt.timedelta(days=1), force=True) == 0
    assert len(runner.commands) == 4


def test_the_authorization_ends_with_the_2026_27_season(tmp_path):
    runner = Recorder()
    last = dt.datetime(2027, 6, 29, 18, 0)  # un mardi
    assert last.weekday() == 1 and passage("mardi", tmp_path, runner, last) == 0
    late = dt.datetime(2027, 7, 6, 18, 0)  # le mardi suivant
    assert passage("mardi", tmp_path, Recorder(), late) == 4
    assert "autorisation échue" in (tmp_path / "passages.log").read_text(encoding="utf-8")


def test_the_season_follows_the_calendar():
    assert pl.season_year(dt.date(2026, 11, 3)) == 2026 and pl.season_year(dt.date(2027, 6, 29)) == 2026
    assert pl.season_year(dt.date(2027, 7, 1)) == 2027 and pl.season_year(dt.date(2027, 1, 5)) == 2026


@pytest.mark.parametrize(
    "command",
    [
        ("-m", "foot_predictor.collect.api_football", "run", "--max-requests", "5"),  # API payante
        ("-m", "foot_predictor.ingestion", "load", "--confirm-db", "x"),
        ("-m", pl.INFERENCE_MODULE, "models", "--activate", "v"),  # sous-commande hors liste
        ("-m", pl.FIXTURES_MODULE, "season", "--season", "2026"),  # sans plafond
        ("-m", pl.FIXTURES_MODULE, "season", "--season", "2026", "--max-requests", "11"),  # plafond dépassé
        ("-m", pl.FIXTURES_MODULE, "fixtures", "--max-requests", "2"),
        ("-m", pl.FIXTURES_MODULE, "fixtures", "--max-requests", "0"),
        ("-m", pl.INFERENCE_MODULE, "live", "--save", "--sealed-test"),
        ("pytest",),
        ("-c", "print(1)"),
    ],
)
def test_the_closed_list_refuses_everything_else(command):
    with pytest.raises(pl.CommandRefused):
        pl.check_command(command)


def test_every_command_of_every_passage_passes_the_closed_list_and_collection_is_capped():
    requests_by_collection = 0
    for p in pl.PASSAGES.values():
        for step in p.steps:
            for command in pl.step_commands(step, dt.date(2026, 11, 3)):
                pl.check_command(command)
                assert "api_football" not in " ".join(command)
                if command[1] == pl.FIXTURES_MODULE:
                    assert "--max-requests" in command
                    if p.name == "mardi":
                        requests_by_collection += int(command[command.index("--max-requests") + 1])
    assert requests_by_collection == 11  # un passage de collecte : 1 + 10
    collecting = [p for p in pl.PASSAGES.values() if "collecte" in p.steps]
    assert len(collecting) * 11 == 22  # le plafond hebdomadaire de l'ADR


def test_next_occurrence_is_the_next_planned_weekday_at_the_planned_time():
    assert pl.next_occurrence(pl.PASSAGES["mardi"], dt.date(2026, 11, 1)) == dt.datetime(2026, 11, 3, 18, 0)
    assert pl.next_occurrence(pl.PASSAGES["mardi"], dt.date(2026, 11, 3)) == dt.datetime(2026, 11, 3, 18, 0)
    assert pl.next_occurrence(pl.PASSAGES["vendredi"], dt.date(2026, 11, 1)) == dt.datetime(2026, 11, 6, 17, 0)
    assert pl.next_occurrence(pl.PASSAGES["samedi"], dt.date(2026, 11, 1)) == dt.datetime(2026, 11, 7, 8, 0)


def test_the_task_xml_is_a_weekly_catch_up_task_under_the_user_session(tmp_path):
    p = pl.PASSAGES["vendredi"]
    root = ET.fromstring(
        pl.task_xml(p, "PC\\leona", dt.date(2026, 11, 1), tmp_path, "C:\\uv\\uv.exe").split("?>", 1)[1]
    )
    trigger = root.find("t:Triggers/t:CalendarTrigger", NS)
    assert trigger.find("t:StartBoundary", NS).text == "2026-11-06T17:00:00"
    assert trigger.find("t:EndBoundary", NS).text == "2027-06-30T23:00:00"  # fin de l'autorisation
    assert trigger.find("t:ScheduleByWeek/t:DaysOfWeek/t:Friday", NS) is not None
    settings = root.find("t:Settings", NS)
    assert settings.find("t:StartWhenAvailable", NS).text == "true" and settings.find("t:WakeToRun", NS).text == "true"
    assert settings.find("t:DisallowStartIfOnBatteries", NS).text == "false"
    assert root.find("t:Principals/t:Principal/t:LogonType", NS).text == "InteractiveToken"  # pas de mot de passe
    exec_ = root.find("t:Actions/t:Exec", NS)
    arguments = exec_.find("t:Arguments", NS).text
    assert arguments.endswith("-m foot_predictor.planification run vendredi") and "--directory" in arguments
    assert exec_.find("t:Command", NS).text == "C:\\uv\\uv.exe"
    assert "api_football" not in arguments and "load" not in arguments.split()


def test_install_without_apply_creates_nothing():
    calls = []
    lines = pl.install(apply=False, today=dt.date(2026, 11, 1), run=lambda *a: calls.append(a))
    assert calls == [] and "Simulation" in lines[-1] and sum("FootPredictor_live_" in line for line in lines) == 3


def test_install_uninstall_and_status_use_schtasks_with_the_three_names():
    calls = []

    def fake(*args):
        calls.append(args)
        return done()

    lines = pl.install(apply=True, today=dt.date(2026, 11, 1), user="PC\\leona", run=fake)
    assert [c[:3] for c in calls] == [
        ("/Create", "/TN", f"FootPredictor_live_{n}") for n in ("mardi", "vendredi", "samedi")
    ]
    assert all(c[3] == "/XML" and c[-1] == "/F" for c in calls) and all("créée" in line for line in lines[3:])
    calls.clear()
    pl.uninstall(run=fake)
    assert [c[:3] for c in calls] == [
        ("/Delete", "/TN", f"FootPredictor_live_{n}") for n in ("mardi", "vendredi", "samedi")
    ]
    calls.clear()
    assert "présente" in pl.status(run=fake)[0] and [c[0] for c in calls] == ["/Query"] * 3


def test_the_log_helpers_keep_the_last_lines_only():
    assert pl.tail("a\n\nb\nc\nd", 2) == "c | d"
    assert len(pl.tail("x" * 5000)) == 1500
