"""YAML de rapprochement : schéma, unicité, absence de cycle (fichiers du dépôt et cas d'erreur)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from foot_predictor.collect.api_football.plan import load_config
from foot_predictor.ingestion import yaml_mappings as ym

REPO = Path(__file__).resolve().parents[2]


def write(directory: Path, name: str, data: dict) -> None:
    (directory / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_repository_yaml_files_are_valid():
    mappings = ym.load_all()
    assert mappings["division_to_league"]["E0"] == 39
    teams, hors_api, non_apparies = mappings["football_data_teams"]
    assert teams and hors_api is not None and isinstance(non_apparies, dict)
    assert all(isinstance(pid, int) for pair in mappings["player_aliases"].items() for pid in pair)
    assert mappings["player_collision_exceptions"] == {}


def test_competitions_are_collected_leagues():
    config = load_config(REPO / "config" / "collecte_api_football.yaml")
    collected = {league for blocks in config.tiers.values() for block in blocks for league in block.leagues}
    assert set(ym.division_to_league().values()) <= collected


def test_player_yaml_files_contain_no_names():
    for name in ("player_aliases.yaml", "player_collisions.yaml"):
        data = yaml.safe_load((ym.MAPPINGS_DIR / name).read_text(encoding="utf-8"))
        values = [v for item in data.values() for v in (item.items() if isinstance(item, dict) else item)]
        assert all(isinstance(k, int) and isinstance(v, int) for k, v in values) or not values


@pytest.mark.parametrize(
    ("aliases", "message"),
    [
        ({5: 5}, "lui-même"),
        ({5: 6, 6: 7}, "à la fois principal et secondaire"),  # chaîne
        ({5: 6, 6: 5}, "à la fois principal et secondaire"),  # cycle
        ({5: "six"}, "entières"),
    ],
)
def test_bad_aliases_are_rejected(tmp_path, aliases, message):
    write(tmp_path, "player_aliases.yaml", {"aliases": aliases})
    with pytest.raises(ym.MappingError, match=message):
        ym.player_aliases(tmp_path)


def test_team_name_in_two_sections_is_rejected(tmp_path):
    write(tmp_path, "football_data_team_ids.yaml", {"teams": {"A": 1}, "hors_api": ["A"], "non_apparies": {}})
    with pytest.raises(ym.MappingError, match="deux sections"):
        ym.football_data_teams(tmp_path)


def test_two_divisions_on_one_league_are_rejected(tmp_path):
    write(tmp_path, "competitions.yaml", {"football_data": {"E0": 39, "E1": 39}})
    with pytest.raises(ym.MappingError, match="même compétition"):
        ym.division_to_league(tmp_path)


@pytest.mark.parametrize(
    "item",
    [
        {"fixture": 1, "player": 2, "action": "keep"},  # preuve absente
        {"fixture": 1, "player": 2, "action": "split", "preuve": "x"},
        {"fixture": 1, "player": 2, "action": "keep", "preuve": "  "},
    ],
)
def test_bad_collision_exceptions_are_rejected(tmp_path, item):
    write(tmp_path, "player_collisions.yaml", {"exceptions": [item]})
    with pytest.raises(ym.MappingError):
        ym.player_collision_exceptions(tmp_path)


def test_collision_exceptions_are_read(tmp_path):
    item = {"fixture": 1, "player": 2, "action": "keep", "preuve": "numéro 8 dans les deux blocs"}
    write(tmp_path, "player_collisions.yaml", {"exceptions": [item]})
    assert ym.player_collision_exceptions(tmp_path) == {(1, 2): "keep"}
    write(tmp_path, "player_collisions.yaml", {"exceptions": [item, item]})
    with pytest.raises(ym.MappingError, match="double"):
        ym.player_collision_exceptions(tmp_path)


# --- Existence dans le brut : sur la machine qui a le brut seulement -------------------------


@pytest.mark.raw
@pytest.mark.skipif(not os.getenv("FP_RAW_DIR"), reason="brut absent (FP_RAW_DIR non défini)")
def test_yaml_identifiers_exist_in_raw():
    from foot_predictor.ingestion import raw_api
    from foot_predictor.ingestion.football_data_csv import read_matches

    raw_dir, external = Path(os.environ["FP_RAW_DIR"]), Path(os.getenv("FP_EXTERNAL_RAW_DIR", "data/raw"))
    divisions = ym.division_to_league()
    api_teams, fd_names = set(), set()
    for league, season in raw_api.league_seasons(raw_dir):
        for fixture in raw_api.listed_fixtures(raw_dir, league, season):
            api_teams |= {fixture.home_id, fixture.away_id}
    for division in divisions:
        for season in range(2000, 2027):
            fd_names |= {name for m in read_matches(external, division, season) for name in (m.home, m.away)}
    teams, hors_api, non_apparies = ym.football_data_teams()
    assert set(teams.values()) <= api_teams
    assert set(teams) | hors_api | set(non_apparies) == fd_names

    players = set()
    for path in (raw_dir / "api_football" / "players").rglob("*.json.gz"):
        players |= {(e.get("player") or {}).get("id") for e in raw_api.response(path)}
    for path in (raw_dir / "api_football" / "player_profiles").rglob("*.json.gz"):
        players |= {(e.get("player") or {}).get("id") for e in raw_api.response(path)}
    aliases = ym.player_aliases()
    assert set(aliases) | set(aliases.values()) <= players
