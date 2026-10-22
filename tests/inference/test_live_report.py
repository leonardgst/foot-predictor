"""Commande et rapport du live (5.14) : part d'indisponibles du top 5, critère de l'ADR-0011, aucune base."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from foot_predictor.inference import live_report
from foot_predictor.inference.availability import AVAILABLE, OUT_OF_SCOPE, UNAVAILABLE, Freshness
from foot_predictor.inference.models import LoadedModel
from foot_predictor.seal import H1_SEALED_EXPERIMENT, SEALED_DONE
from tests.inference.test_predict import FakeModel, context, day_of, shifted_matches

DAY = dt.date(2026, 10, 24)


def answer(status, reasons=(), market=None, version="final"):
    return {"status": status, "reasons": list(reasons), "market_reference": market, "model_version": version}


class Ctx:
    today = DAY
    data_version = "load_run-7+fd-abc"
    league_freshness = {39: Freshness("football-data (live)", DAY, dt.datetime(2026, 10, 22, 14, tzinfo=dt.UTC))}
    live_summary = {"files_version": "fd-abc", "counts": {"resultats_superposes": 8}, "issues": []}


def test_share_of_unavailable_matches_counts_the_top5_only_against_the_one_in_five_limit():
    stale = "variables d'historique périmées : football-data complet jusqu'au 2026-10-22"
    answers = {
        DAY: [answer(AVAILABLE, market={"p_over_2_5": 0.5}), answer(AVAILABLE), answer(UNAVAILABLE, [stale]),
              answer(OUT_OF_SCOPE, ["hors périmètre du modèle H1 (championnat hors du top 5)"])],
        DAY + dt.timedelta(days=1): [answer(AVAILABLE), answer(AVAILABLE)],
    }  # fmt: skip
    report = live_report.summarize(answers, Ctx())
    assert report["matches"] == 5 and report["available"] == 4 and report["unavailable_share"] == pytest.approx(0.2)
    assert not report["over_limit"]  # un sur cinq exactement : pas au-delà
    assert report["reasons"] == {"variables d'historique périmées": 1} and report["with_market_reference"] == 1
    assert report["days"][0] == {"day": "2026-10-24", "matches": 3, "statuses": {AVAILABLE: 2, UNAVAILABLE: 1},
                                 "out_of_scope": 1}  # fmt: skip
    answers[DAY].append(answer(UNAVAILABLE, [stale]))
    worse = live_report.summarize(answers, Ctx())
    assert worse["over_limit"] and "au-delà du critère" in live_report.render(worse)
    text = live_report.render(report)
    assert "20% d'indisponibles (1 sur 5)" in text and "| 2026-10-24 | 3 | 2 | unavailable 1 | 1 |" in text


def test_no_match_in_the_window_is_not_a_failure():
    report = live_report.summarize({DAY: [answer(OUT_OF_SCOPE)]}, Ctx())
    assert report["matches"] == 0 and report["unavailable_share"] is None and not report["over_limit"]
    assert "aucun match du top 5" in live_report.render(report)


def test_live_command_writes_its_report_and_lists_the_top5(tmp_path, monkeypatch, capsys):
    from foot_predictor.inference import __main__ as cli
    from foot_predictor.inference import check
    from foot_predictor.inference import context as context_module

    matches = shifted_matches(years=6)
    log = tmp_path / "journal.md"
    log.write_text(f"| x | y | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport z |\n", encoding="utf-8")
    upcoming = day_of(matches, lambda m: m["status"] != "played")
    loaded = LoadedModel("essai", FakeModel(), {"version": "essai"}, None)
    ctx = context(matches, loaded, sealed_log=log, today=upcoming["match_day"], history_opened=True)
    monkeypatch.setattr(context_module, "build_context", lambda: ctx)
    written = {}
    monkeypatch.setattr(check, "write_report", lambda report, name, md: written.update(name=name, md=md, report=report)
                        or (tmp_path / f"{name}.json", tmp_path / f"{name}.md"))  # fmt: skip
    assert cli.main(["live", "--days", "2", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out.split("\n]\n")[0] + "\n]")
    assert listed and all(a["mode"] == "live" and a["status"] != OUT_OF_SCOPE for a in listed)
    assert written["name"] == f"live_{upcoming['match_day'].isoformat()}" and "saved" not in written["report"]
    assert written["report"]["matches"] == len(listed)


def test_live_save_writes_only_available_predictions(tmp_path, monkeypatch):
    """Une ligne « indisponible » bloquerait, par idempotence, la prédiction devenue disponible plus tard."""
    from foot_predictor.inference import __main__ as cli
    from foot_predictor.inference import check
    from foot_predictor.inference import context as context_module

    matches = shifted_matches(years=6)
    log = tmp_path / "journal.md"
    log.write_text(f"| x | y | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport z |\n", encoding="utf-8")
    upcoming = day_of(matches, lambda m: m["status"] != "played")
    loaded = LoadedModel("essai", FakeModel(), {"version": "essai"}, None)
    ctx = context(matches, loaded, sealed_log=log, today=upcoming["match_day"], history_opened=True)
    stale = {"match_id": -1, "status": UNAVAILABLE, "reasons": ["variables d'historique périmées : …"],
             "market_reference": None}  # fmt: skip
    monkeypatch.setattr(context_module, "build_context", lambda: ctx)
    monkeypatch.setattr(check, "write_report", lambda report, name, md: (tmp_path / "a.json", tmp_path / "a.md"))
    real_predict = __import__("foot_predictor.inference.predict", fromlist=["predict_day"]).predict_day
    monkeypatch.setattr("foot_predictor.inference.predict.predict_day",
                        lambda day, mode, c: real_predict(day, mode, c) + [stale | {"model_version": "essai"}])  # fmt: skip
    sent = []
    monkeypatch.setattr(cli, "save_answers", lambda answers, reference: sent.extend(answers) or {"created": len(answers),
                        "kept": 0, "refused": 0})  # fmt: skip
    assert cli.main(["live", "--days", "1", "--save", "--json"]) == 0
    assert sent and all(a["status"] == AVAILABLE for a in sent)


def test_live_command_refuses_a_closed_history(monkeypatch, capsys):
    from foot_predictor.inference import __main__ as cli
    from foot_predictor.inference import context as context_module

    matches = shifted_matches()
    ctx = context(matches, LoadedModel("essai", FakeModel(), {"version": "essai"}, None))  # table non ouverte
    monkeypatch.setattr(context_module, "build_context", lambda: ctx)
    assert cli.main(["live"]) == 3 and "test scellé H1" in capsys.readouterr().err
