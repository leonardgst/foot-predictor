"""Matrice de disponibilité (décision 6 de la partie 5 ; rapport F.5 ; ADR-0011, règle 5 ; ADR-0040).

Pour un match, chaque variable requise par le modèle, pour chaque équipe, reçoit un statut :

- **présente** : la valeur est calculée ;
- **manquante** : incalculable, avec la raison (pas d'historique de championnat sur 730 jours,
  pas de tirs connus, équipe inconnue du référentiel…) ;
- **périmée** : la source ne contient pas encore tous les matchs antérieurs au jour du match
  (sa dernière mise à jour est trop ancienne), avec la raison et la date de la source.

Le match reçoit ensuite un statut global :

| Statut | Sens | Prédiction |
|---|---|---|
| `available` | toutes les variables requises sont présentes | oui |
| `unavailable` | au moins une variable manquante ou périmée ; raisons listées | **non** |
| `out_of_scope` | match hors du périmètre du modèle H1 (D2, coupe, barrage, autre championnat) | non |
| `excluded` | match annulé, abandonné ou sur tapis vert (ADR-0009) | non |
| `h2_unavailable` | horizon H2 demandé : pas avant la partie 6 | non |

Jamais de valeur de remplacement : une variable non présente bloque la prédiction.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field

import pandas as pd

from foot_predictor.features.leagues import TOP5

PRESENT, MISSING, STALE = "presente", "manquante", "perimee"
AVAILABLE, UNAVAILABLE, OUT_OF_SCOPE, EXCLUDED, H2_UNAVAILABLE = (
    "available", "unavailable", "out_of_scope", "excluded", "h2_unavailable",
)  # fmt: skip

HISTORY_PREFIXES = ("elo_", "opp_elo_", "goals_", "opp_goals_", "xgp_", "opp_xgp_")
"""Variables calculées sur l'historique des matchs : elles peuvent être périmées ; le contexte (G0), non."""


@dataclass(frozen=True)
class Freshness:
    """État d'une source d'historique : jusqu'à quel jour elle contient **tous** les matchs joués."""

    source: str
    complete_until: dt.date
    """Dernier jour dont tous les matchs terminés sont connus de la source."""
    last_update: dt.datetime | None = None

    def is_stale_for(self, day: dt.date) -> bool:
        """Périmée pour le jour J si elle ne couvre pas tous les jours antérieurs à J."""
        return self.complete_until < day - dt.timedelta(days=1)


@dataclass
class VariableStatus:
    variable: str
    side: str  # « domicile » ou « exterieur »
    status: str
    value: float | int | None = None
    reason: str | None = None
    source_date: str | None = None


@dataclass
class Availability:
    match_id: int
    status: str
    reasons: list[str] = field(default_factory=list)
    variables: list[VariableStatus] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        return self.status == AVAILABLE

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "status": self.status,
            "reasons": self.reasons,
            "variables": [asdict(v) for v in self.variables],
        }


def missing_reason(variable: str) -> str:
    """Raison lisible d'une variable vide (toutes viennent de `features/`, jamais remplies)."""
    base = variable.removeprefix("opp_")
    whose = "de l'adversaire" if variable.startswith("opp_") else "de l'équipe"
    if base.startswith("xgp_"):
        return f"aucun match de championnat {whose} avec tirs connus dans les 730 jours"
    if base.startswith("goals_"):
        return f"aucun match de championnat {whose} dans les 730 jours"
    if base.startswith("elo_"):
        return f"note Elo {whose} indisponible (équipe hors des échelles nationales)"
    return f"valeur {whose} incalculable"


def _value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return None
    return value.item() if hasattr(value, "item") else value


def match_availability(
    match: pd.Series,
    rows: pd.DataFrame,
    features: tuple[str, ...],
    freshness: Freshness | None = None,
    horizon: str = "H1",
) -> Availability:
    """Disponibilité d'un match : `match` (une ligne de la table des matchs), `rows` (ses lignes d'inférence)."""
    match_id = int(match["match_id"])
    if horizon != "H1":
        return Availability(match_id, H2_UNAVAILABLE, ["horizon H2 (avec composition) : pas avant la partie 6"])
    if bool(match.get("excluded", False)):
        return Availability(match_id, EXCLUDED, [f"match exclu ({match.get('exclusion_reason') or 'ADR-0009'})"])
    if match.get("api_league_id") not in TOP5:
        kind = "coupe" if match.get("competition_kind") == "cup" else "championnat hors du top 5"
        return Availability(match_id, OUT_OF_SCOPE, [f"hors périmètre du modèle H1 ({kind}) : pas de prédiction"])
    if not bool(match.get("is_regular_season", True)):
        return Availability(
            match_id, OUT_OF_SCOPE, ["barrage ou tour hors saison régulière : hors périmètre du modèle H1"]
        )
    if len(rows) != 2:
        return Availability(match_id, UNAVAILABLE, ["lignes du match incalculables (équipe inconnue du référentiel)"])

    day = match["match_day"] if isinstance(match["match_day"], dt.date) else pd.Timestamp(match["match_day"]).date()
    stale = freshness is not None and freshness.is_stale_for(day)
    variables, reasons = [], []
    for _, row in rows.sort_values("is_home", ascending=False).iterrows():
        side = "domicile" if row["is_home"] else "exterieur"
        for name in features:
            value = _value(row.get(name))
            if stale and name.startswith(HISTORY_PREFIXES):
                reason = (
                    f"source {freshness.source} complète jusqu'au {freshness.complete_until.isoformat()} seulement "
                    f"(il faut tous les matchs d'avant le {day.isoformat()})"
                )
                variables.append(VariableStatus(name, side, STALE, value, reason, freshness.complete_until.isoformat()))
                reasons.append(f"variables d'historique périmées : {reason}")  # une seule raison par source
            elif value is None:
                reason = missing_reason(name)
                variables.append(VariableStatus(name, side, MISSING, None, reason))
                reasons.append(f"{name} ({side}) manquante : {reason}")
            else:
                source_date = freshness.complete_until.isoformat() if freshness else None
                variables.append(VariableStatus(name, side, PRESENT, value, None, source_date))
    status = UNAVAILABLE if reasons else AVAILABLE
    return Availability(match_id, status, _unique(reasons), variables)


def _unique(reasons: list[str]) -> list[str]:
    seen, out = set(), []
    for reason in reasons:
        if reason not in seen:
            out.append(reason)
            seen.add(reason)
    return out
