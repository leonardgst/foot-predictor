"""Cotes plus/moins 2,5 buts des CSV football-data : choix de la colonne, ligne par ligne (ADR-0036).

Le marché est une **référence** du protocole (décision M18, rapport I.6), jamais une
variable. Deux versions :

- `avant_cloture` : cotes relevées avant le match (colonnes sans `C`) ; référence de
  l'horizon H1 (ADR-0010) ;
- `cloture` : cotes de clôture (colonnes `C`) ; **borne haute**, jamais une variable ni une
  référence de l'horizon H1 (rapport I.8 : la clôture contient l'information du jour du match).

Les noms de colonnes changent d'une saison à l'autre (en-têtes réels des 270 fichiers,
lus le 2026-09-30) :

| Colonnes (> 2,5 et < 2,5) | Saisons | Nature |
|---|---|---|
| `Avg`, `AvgC` | 2019-20 et après | moyenne de marché (football-data ne publie pas le nombre de cotes) |
| `BbAv` (+ `BbOU`) | 2005-06 à 2018-19 | agrégat historique BetBrain, `BbOU` bookmakers ; avant clôture seulement |
| `B365`, `B365C` | 2002-03 à 2004-05, puis 2019-20 et après | un bookmaker (Bet365) |
| `P`, `PC` | 2019-20 à 2025-26 | un bookmaker (Pinnacle) |
| `BFE`, `BFEC` | 2024-25 et après | bourse Betfair |
| `GB` | 2002-03 à 2004-05 | un bookmaker (Gamebookers) |
| (aucune) | 2000-01 et 2001-02 | pas de cote plus/moins 2,5 |

`Max`, `MaxC`, `BbMx` (meilleure cote du marché) ne sont jamais retenus : un maximum n'est
pas une estimation de probabilité. Aucune cote de clôture n'existe avant 2019-20.

**Ordre de priorité**, pour chaque ligne et chaque version : la première colonne dont les
deux cotes (> 2,5 et < 2,5) sont lisibles et supérieures à 1 ; sinon, aucune cote (jamais
inventée). Moyenne de marché, puis agrégat historique, puis un bookmaker (Bet365, le plus
continu ; Pinnacle ; Betfair ; Gamebookers).
"""

from __future__ import annotations

from dataclasses import dataclass

AVANT_CLOTURE = "avant_cloture"
CLOTURE = "cloture"
VERSIONS = (AVANT_CLOTURE, CLOTURE)


@dataclass(frozen=True)
class OddsColumn:
    prefix: str
    """Préfixe des colonnes : `<prefix>>2.5` et `<prefix><2.5`."""
    kind: str
    """`moyenne_marche`, `agregat_historique` ou `bookmaker`."""
    count_column: str | None = None
    """Colonne du nombre de cotes agrégées (`BbOU`), s'il est publié."""


PRIORITY: dict[str, tuple[OddsColumn, ...]] = {
    AVANT_CLOTURE: (
        OddsColumn("Avg", "moyenne_marche"),
        OddsColumn("BbAv", "agregat_historique", count_column="BbOU"),
        OddsColumn("B365", "bookmaker"),
        OddsColumn("P", "bookmaker"),
        OddsColumn("BFE", "bookmaker"),
        OddsColumn("GB", "bookmaker"),
    ),
    CLOTURE: (
        OddsColumn("AvgC", "moyenne_marche"),
        OddsColumn("B365C", "bookmaker"),
        OddsColumn("PC", "bookmaker"),
        OddsColumn("BFEC", "bookmaker"),
    ),
}


@dataclass(frozen=True)
class Odds:
    version: str
    over: float
    under: float
    column: str
    """Préfixe de la colonne retenue (`Avg`, `BbAv`, `B365`…)."""
    n_odds: int | None
    """Nombre de cotes agrégées : `BbOU` pour BetBrain, 1 pour un bookmaker, vide s'il n'est pas publié."""


def odds_value(value: str | None) -> float | None:
    """Cote décimale lisible et supérieure à 1, sinon None (une cote ≤ 1 n'a pas de sens)."""
    try:
        number = float(value) if value not in (None, "") else None
    except ValueError:
        return None
    return number if number is not None and number > 1.0 else None


def _count(row: dict, column: OddsColumn) -> int | None:
    if column.kind == "bookmaker":
        return 1
    if column.count_column is None:
        return None
    try:
        count = int(float(row.get(column.count_column) or ""))
    except ValueError:
        return None
    return count if count > 0 else None


def select_odds(row: dict, version: str) -> Odds | None:
    """Cotes plus/moins 2,5 d'une ligne de CSV pour `version`, selon l'ordre de `PRIORITY`."""
    for column in PRIORITY[version]:
        over = odds_value(row.get(f"{column.prefix}>2.5"))
        under = odds_value(row.get(f"{column.prefix}<2.5"))
        if over is not None and under is not None:
            return Odds(version, over, under, column.prefix, _count(row, column))
    return None


def implied_probability_over(over: float, under: float) -> float:
    """P(T > 2,5) implicite, marge retirée par normalisation proportionnelle.

    Avec q₊ = 1/cote₊ et q₋ = 1/cote₋ (leur somme dépasse 1 de la marge du bookmaker) :
    P(T > 2,5) = q₊ / (q₊ + q₋).
    """
    q_over, q_under = 1.0 / over, 1.0 / under
    return q_over / (q_over + q_under)
