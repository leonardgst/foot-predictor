"""Registre des variables : validité, horizons, développement des demi-vies et de la portée."""

from __future__ import annotations

import pytest
import yaml

from foot_predictor.features import registry


def test_the_registry_is_valid():
    entries = registry.load_entries()
    assert entries
    variables = registry.variables()
    assert len({v.name for v in variables}) == len(variables)


def test_no_variable_without_horizon_and_only_h1():
    for variable in registry.variables():
        assert variable.horizon, variable.name
        if variable.group in registry.FEATURE_GROUPS:
            assert variable.horizon == "H1", variable.name


def test_candidate_half_lives_are_distinct_variables_carrying_their_parameter():
    by_name = {v.name: v for v in registry.variables()}
    for h in (60, 120, 240):
        assert by_name[f"goals_for_ewm_h{h}"].parameters["demi_vie_jours"] == h
        assert by_name[f"opp_xgp_against_ewm_h{h}"].parameters["demi_vie_jours"] == h
        assert "{h}" not in by_name[f"goals_for_ewm_h{h}"].missing


def test_opponent_columns_follow_the_scope():
    names = set(registry.columns())
    assert {"elo_pre", "opp_elo_pre", "rest_days", "opp_rest_days", "team_id", "opp_team_id"} <= names
    assert "opp_is_home" not in names and "opp_rest_reliable" not in names


def test_g3_is_not_available_live():
    """ADR-0011 : les coupes ne sont couvertes par aucune source gratuite après l'abonnement."""
    for variable in registry.variables():
        if variable.group == "G3":
            assert variable.live.startswith("non"), variable.name


def test_the_target_is_not_a_feature():
    assert "goals_for" not in registry.feature_columns()
    assert "goals_against" not in registry.feature_columns()


def _write(tmp_path, entry):
    path = tmp_path / "registre.yaml"
    path.write_text(yaml.safe_dump({"variables": [entry]}, allow_unicode=True), encoding="utf-8")
    return path


BASE = {
    "nom": "x",
    "portee": ["equipe"],
    "groupe": "G1",
    "definition": "d",
    "source": "s",
    "horizon": "H1",
    "disponible_en_live": "oui",
    "parametres": {},
    "historique_minimal": "aucun",
    "manquant": "vide",
    "risque_fuite": "nul",
    "parade": "p",
}


@pytest.mark.parametrize(
    "change",
    [
        {"horizon": ""},  # variable sans horizon
        {"horizon": "H2"},  # H2 interdit au MVP
        {"groupe": "G9"},
        {"portee": ["adversaire"]},
        {"nom": "x_h{h}"},  # « {h} » sans demi-vies
        {"definition": None},
    ],
)
def test_invalid_entries_are_refused(tmp_path, change):
    with pytest.raises(registry.RegistryError):
        registry.variables(_write(tmp_path, BASE | change))


def test_sha256_changes_with_the_file(tmp_path):
    a = registry.sha256(_write(tmp_path, BASE))
    b = registry.sha256(_write(tmp_path, BASE | {"definition": "autre"}))
    assert a != b and len(a) == 64
