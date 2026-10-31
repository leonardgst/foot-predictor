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


def test_no_variable_without_horizon_and_each_group_has_its_horizon():
    for variable in registry.variables():
        assert variable.horizon, variable.name
        if variable.group in registry.FEATURE_GROUPS:
            assert variable.horizon == registry.GROUP_HORIZON[variable.group], variable.name


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
        {"horizon": "H2"},  # G1 est de l'horizon H1
        {"groupe": "G6"},  # G6 (stabilité) est de l'horizon H2, pas H1
        {"groupe": "G7", "horizon": "H2"},  # G7 (blessures) hors périmètre (ADR-0047)
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


@pytest.mark.parametrize("group", ["G4", "G5", "G6"])
def test_composition_groups_are_accepted_at_horizon_h2(tmp_path, group):
    """ADR-0047 : entraîneur de la feuille de match, qualité du XI, stabilité."""
    (variable,) = registry.variables(_write(tmp_path, BASE | {"groupe": group, "horizon": "H2"}))
    assert (variable.group, variable.horizon) == (group, "H2")


def _two_horizons(tmp_path):
    path = tmp_path / "registre.yaml"
    entries = [BASE | {"nom": "elo"}, BASE | {"nom": "xi_overlap_prev", "groupe": "G6", "horizon": "H2"}]
    path.write_text(yaml.safe_dump({"variables": entries}, allow_unicode=True), encoding="utf-8")
    return path


def test_an_h1_model_refuses_an_h2_variable(tmp_path):
    path = _two_horizons(tmp_path)
    registry.check_model_horizon(["elo"], "H1", path)
    with pytest.raises(registry.RegistryError, match="plus tardif"):
        registry.check_model_horizon(["elo", "xi_overlap_prev"], "H1", path)


def test_an_h2_model_reads_both_horizons(tmp_path):
    registry.check_model_horizon(["elo", "xi_overlap_prev"], "H2", _two_horizons(tmp_path))


@pytest.mark.parametrize(("columns", "horizon"), [(["inconnue"], "H2"), (["elo"], "H3")])
def test_unknown_columns_and_horizons_are_refused(tmp_path, columns, horizon):
    with pytest.raises(registry.RegistryError):
        registry.check_model_horizon(columns, horizon, _two_horizons(tmp_path))


def test_the_final_h1_model_passes_the_horizon_guard():
    """Garde H1 (ADR-0044) : les 13 colonnes du modèle H1 retenu sont toutes au registre, toutes H1."""
    from foot_predictor.modeling.models.team import M3

    registry.check_model_horizon(list(M3(groups=("G0", "G1", "G2"), half_life=240).features), "H1")
