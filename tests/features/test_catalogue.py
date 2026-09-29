"""Le catalogue des variables est généré depuis le registre et reste à jour."""

from __future__ import annotations

from foot_predictor.features import catalogue, registry


def test_catalogue_is_up_to_date():
    """Échoue si le registre a changé sans régénérer : python -m foot_predictor.features catalogue."""
    on_disk = catalogue.CATALOGUE_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert on_disk == catalogue.render()


def test_catalogue_lists_every_column():
    text = catalogue.render()
    for name in registry.columns():
        assert f"`{name}`" in text, name
