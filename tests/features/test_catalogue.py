"""Le catalogue des variables est généré depuis le registre et reste à jour."""

from __future__ import annotations

import yaml

from foot_predictor.features import catalogue, registry


def test_catalogue_is_up_to_date():
    """Échoue si le registre a changé sans régénérer : python -m foot_predictor.features catalogue."""
    on_disk = catalogue.CATALOGUE_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert on_disk == catalogue.render()


def test_catalogue_lists_every_column():
    text = catalogue.render()
    for name in registry.columns():
        assert f"`{name}`" in text, name


def test_catalogue_announces_h2_groups_when_the_registry_has_them(tmp_path):
    entries = registry.load_entries()
    h2 = {
        "nom": "xi_demo",
        "portee": ["equipe"],
        "groupe": "G6",
        "definition": "essai",
        "source": "essai",
        "horizon": "H2",
        "disponible_en_live": "non",
        "parametres": {},
        "historique_minimal": "un match",
        "manquant": "vide",
        "risque_fuite": "nul",
        "parade": "jours antérieurs",
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"variables": [*entries, h2]}, allow_unicode=True), encoding="utf-8")
    text = catalogue.render(path)
    assert "(G0 à G6)" in text and "horizon H2" in text and "`xi_demo`" in text
