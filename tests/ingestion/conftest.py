"""Fixtures partagées des tests d'ingestion.

`multi_config` (P1 : ligue 39, P3 : ligue 88, saisons 2015-2016) vient des tests de
raw_check : le chargeur et les collisions sont testés sur les mêmes bruts synthétiques.
"""

from tests.quality.test_raw_check import multi_config  # noqa: F401
