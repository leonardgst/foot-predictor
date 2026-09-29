"""Commande `load` de bout en bout (base de test) et rapport `check-referentiel`."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from foot_predictor.collect import raw_bytes
from foot_predictor.collect.football_data.download import season_dir
from foot_predictor.ingestion.__main__ import main
from foot_predictor.ingestion.pipeline import LoadRefused, run_load
from foot_predictor.ingestion.referentiel_check import run_check
from tests.quality.test_raw_check import build_multi, synthetic


@pytest.fixture
def sources(tmp_path):
    raw = tmp_path / "raw"
    p1 = [synthetic(1001, "2015-08-15", 1, 2, [11, 0], [21]), synthetic(1002, "2015-08-22", 2, 1, [21], [11])]
    for item in p1:
        item["score"] = {"fulltime": {"home": 0, "away": 0}}
    build_multi(raw, p1, []).queue.close()
    external = tmp_path / "externe"
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST\r\nE0,15/08/2015,Club Un,Club Deux,0,0,12,,5,x\r\n"
    raw_bytes.write_bytes(
        external, season_dir(2015), "E0", ".csv", csv.encode(), dt.datetime(2026, 9, 29, tzinfo=dt.UTC)
    )
    return raw, external


@pytest.fixture
def clean_database(_test_engine):
    yield _test_engine
    with _test_engine.begin() as connection:
        connection.execute(text("TRUNCATE staging.competition, staging.team, staging.player, staging.coach CASCADE"))
        connection.execute(text("TRUNCATE ops.load_run CASCADE"))  # et features.dataset_version (0006)


@pytest.mark.db
def test_load_then_check(clean_database, sources, multi_config, tmp_path, monkeypatch):
    engine = clean_database
    raw, external = sources
    # Le YAML du dépôt ne connaît pas ces équipes fictives : on le remplace pour ce test.
    monkeypatch.setattr(
        "foot_predictor.ingestion.yaml_mappings.football_data_teams",
        lambda directory=None: ({"Club Un": 1, "Club Deux": 2}, set(), {}),
    )
    monkeypatch.setattr("foot_predictor.ingestion.yaml_mappings.division_to_league", lambda directory=None: {"E0": 39})
    monkeypatch.setattr("foot_predictor.ingestion.yaml_mappings.player_aliases", lambda directory=None: {})

    summary = run_load(engine, raw, external, engine.url.database, multi_config, tmp_path / "work")
    assert summary["counts"]["fd_rates"] == {"E0:2015": [1, 1]}
    assert summary["fingerprints"]["match"]["rows"] == 2
    with engine.connect() as connection:
        run = connection.execute(text("SELECT status, manifests, counts FROM ops.load_run")).mappings().one()
    assert run["status"] == "ok" and run["manifests"]  # sha256 des journaux lus
    assert run["counts"]["lineup_unknown_entries"] == 1
    with engine.connect() as connection:  # tirs de football-data (ADR-0029) : vides si absents, jamais 0
        shots = connection.execute(
            text(
                "SELECT tm.is_home, e.shots, e.shots_on_target FROM staging.team_match_stats_external e "
                "JOIN staging.team_match tm ON tm.id = e.team_match_id ORDER BY tm.is_home DESC"
            )
        ).all()
    assert [tuple(r) for r in shots] == [(True, 12, 5), (False, None, None)]
    assert summary["fingerprints"]["team_match_stats_external"]["rows"] == 2

    report = run_check(engine, tmp_path / "rapports", today=dt.date(2026, 9, 29)).read_text(encoding="utf-8")
    assert "1 / 1 lignes appariées (100.00 %)" in report and "**OK**" in report
    assert "## 6. Tirs de football-data" in report
    assert "Joueur 1" not in report and "Joueur 2" not in report  # aucun nom de joueur (noms fictifs « Joueur 11 »)

    with pytest.raises(LoadRefused):
        run_load(engine, raw, external, "une_autre_base", multi_config, tmp_path / "work2")
    with engine.connect() as connection:  # un refus n'écrit rien, pas même une trace
        assert connection.execute(text("SELECT count(*) FROM ops.load_run")).scalar_one() == 1


def test_cli_refuses_a_missing_raw_dir(tmp_path, capsys, monkeypatch):
    """Le chemin est vérifié avant la configuration de la base : aucun .env n'est nécessaire."""

    def no_settings():
        raise RuntimeError("configuration de base absente")

    monkeypatch.setattr("foot_predictor.ingestion.__main__.get_settings", no_settings)
    code = main(["load", "--raw-dir", str(tmp_path / "absent"), "--confirm-db", "x"])
    assert code == 2 and "introuvable" in capsys.readouterr().err
