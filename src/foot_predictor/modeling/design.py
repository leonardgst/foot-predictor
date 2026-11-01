"""Matrice des variables des modèles, ajustée **dans le pli** (rapport I.7, I.8 ; ADR-0037).

`Design(groups, half_life, level)` décrit quelles variables entrent dans un modèle. `fit(lignes
d'apprentissage)` apprend tout ce qui dépend des données (modalités des championnats, moyennes et
écarts-types de standardisation) ; `transform(lignes)` construit la matrice, avec une constante.
Rien n'est appris sur les lignes de test.

**Niveau équipe** (`level="team"`, modèles M3 à M6) : une ligne par (match, équipe), cible
`goals_for`. Variables, par groupe (registre des variables, ADR-0030) :

- G0 : `is_home` ; effets fixes de championnat (une indicatrice par championnat, le premier en
  référence) ; `behind_closed_doors` et son interaction avec `is_home` (l'avantage du terrain qui
  s'effondre à huis clos, rapport C.2). `season_year` n'entre pas : une tendance linéaire
  extrapolerait mal d'une saison à l'autre ;
- G1 : `elo_pre` et `opp_elo_pre`, standardisés (l'écart `elo_diff` en est une combinaison) ;
- G2 (demi-vie h) : logarithmes des moyennes glissantes de buts et d'`xg_proxy`, pour et contre,
  de l'équipe et de l'adversaire, standardisés. Le logarithme rend la structure attaque × défense
  additive sous le lien log : λ ∝ attaque_équipe · défense_adversaire ;
- G3 : repos (borné à 14 jours), matchs des 14 derniers jours, match européen dans les 4 jours,
  pour l'équipe et l'adversaire, standardisés ;
- **horizon H2** (ADR-0047, ADR-0048), lignes de l'équipe et de l'adversaire, standardisées dans le pli
  (linéaires, sauf l'indicateur « nouvel entraîneur ») :
  - G6 (stabilité) : titulaires communs avec le match précédent, **une** cohésion (variante `cohesion`
    parmi `h3`, `h5`, `h10`, `h20`, `hinf`, `reset`, `win10`, ou `overlap_only` : le recouvrement seul),
    nombre de nouveaux titulaires ;
  - G5 (qualité du XI) : note rétrécie vers la moyenne du poste, part des habituels absents, âge moyen ;
  - G4 (entraîneur) : ancienneté plafonnée à 365 jours, indicateur « nouvel entraîneur ». G5 et G4
    ont un **début d'apprentissage** (`first_training_season`, D3) : leurs lignes de rodage ne servent pas.

**Niveau match** (`level="match"`, modèles M1 et M2 sur le total) : une ligne par match. G0 :
effets fixes de championnat et huis clos ; G1 : Elo de l'équipe à domicile et de l'équipe à
l'extérieur. (`is_home` n'a pas de sens pour un total.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

GROUPS = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
H2_GROUPS = ("G4", "G5", "G6")
COHESION_VARIANTS = ("h3", "h5", "h10", "h20", "hinf", "reset", "win10", "overlap_only")
FIRST_TRAINING_SEASON_OF = {"G5": 2016, "G4": 2017}
"""Début d'apprentissage des groupes à historique court (ADR-0047, D3) : G5 dès 2016-17, G4 dès 2017-18."""
HALF_LIVES = (60, 120, 240)
REST_CAP_DAYS = 14


def g2_columns(half_life: int) -> list[str]:
    base = [f"goals_for_ewm_h{half_life}", f"goals_against_ewm_h{half_life}"]
    base += [f"xgp_for_ewm_h{half_life}", f"xgp_against_ewm_h{half_life}"]
    return base + [f"opp_{c}" for c in base]


def g6_columns(cohesion: str) -> list[str]:
    """Colonnes de la stabilité pour une variante de cohésion, avec celles de l'adversaire."""
    if cohesion == "overlap_only":
        base = ["xi_overlap_prev"]
    else:
        column = f"xi_cohesion_{'ewm_' if cohesion.startswith('h') else ''}{cohesion}"
        base = ["xi_overlap_prev", column, "xi_new_starters"]
    return base + [f"opp_{c}" for c in base]


G5_BASE = ["xi_quality", "xi_regulars_missing", "xi_mean_age"]
G5_COLUMNS = G5_BASE + [f"opp_{c}" for c in G5_BASE]
G4_BASE = ["coach_tenure_days", "coach_is_new"]
G4_COLUMNS = G4_BASE + [f"opp_{c}" for c in G4_BASE]

G3_COLUMNS = [
    "rest_days", "opp_rest_days", "matches_last_14d", "opp_matches_last_14d",
    "european_match_last_4d", "opp_european_match_last_4d",
]  # fmt: skip


@dataclass
class Design:
    groups: tuple[str, ...] = ("G0", "G1")
    half_life: int | None = None
    level: str = "team"
    cohesion: str | None = None
    """Variante de cohésion de G6 (obligatoire avec G6) ; choisie par validation interne, comme `half_life`."""
    leagues_: list = field(default_factory=list)
    scale_: dict = field(default_factory=dict)
    dropped_: list = field(default_factory=list)
    """Colonnes constantes sur l'apprentissage (huis clos absent d'un pli, par exemple) : retirées."""

    def __post_init__(self) -> None:
        self.groups = tuple(self.groups)
        unknown = set(self.groups) - set(GROUPS)
        if unknown or "G0" not in self.groups:
            raise ValueError(f"Groupes {self.groups} : G0 obligatoire, groupes connus {GROUPS}")
        if "G2" in self.groups and self.half_life not in HALF_LIVES:
            raise ValueError(f"G2 exige une demi-vie parmi {HALF_LIVES}")
        if "G6" in self.groups and self.cohesion not in COHESION_VARIANTS:
            raise ValueError(f"G6 exige une cohésion parmi {COHESION_VARIANTS}, pas {self.cohesion!r}")
        if "G6" not in self.groups and self.cohesion is not None:
            raise ValueError("cohesion sans G6")
        if self.level not in ("team", "match"):
            raise ValueError("level : team ou match")
        if self.level == "match" and set(self.groups) - {"G0", "G1"}:
            raise ValueError("Niveau match : G0 et G1 seulement (modèles pédagogiques M1 et M2)")

    # ------------------------------------------------------------------ colonnes brutes

    def required(self) -> list[str]:
        """Colonnes du jeu de données dont le modèle a besoin (lignes incomplètes exclues par le protocole)."""
        columns = ["is_home", "api_league_id", "behind_closed_doors"]
        if "G1" in self.groups:
            columns += ["elo_pre", "opp_elo_pre"]
        if "G2" in self.groups:
            columns += g2_columns(self.half_life)
        if "G3" in self.groups:
            columns += G3_COLUMNS
        if "G4" in self.groups:
            columns += G4_COLUMNS
        if "G5" in self.groups:
            columns += G5_COLUMNS
        if "G6" in self.groups:
            columns += g6_columns(self.cohesion)
        return columns

    @property
    def first_training_season(self) -> int | None:
        """Première saison d'apprentissage imposée par les groupes à historique court (D3), sinon aucune."""
        starts = [FIRST_TRAINING_SEASON_OF[g] for g in self.groups if g in FIRST_TRAINING_SEASON_OF]
        return max(starts) if starts else None

    # ------------------------------------------------------------------ construction

    def _raw(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Variables continues avant standardisation, et variables binaires (même index que `rows`)."""
        if self.level == "match":
            frame = pd.DataFrame(index=rows.index)
            frame["behind_closed_doors"] = rows["home_behind_closed_doors"].astype(float)
            if "G1" in self.groups:
                frame["z_home_elo"] = rows["home_elo_pre"].astype(float)
                frame["z_away_elo"] = rows["away_elo_pre"].astype(float)
            return frame
        frame = pd.DataFrame(index=rows.index)
        home = rows["is_home"].astype(float)
        closed = rows["behind_closed_doors"].astype(float)
        frame["is_home"] = home
        frame["behind_closed_doors"] = closed
        frame["home_x_closed"] = home * closed
        if "G1" in self.groups:
            frame["z_elo"] = rows["elo_pre"].astype(float)
            frame["z_opp_elo"] = rows["opp_elo_pre"].astype(float)
        if "G2" in self.groups:
            for column in g2_columns(self.half_life):
                # Moyennes retirées vers le championnat (ADR-0032), strictement positives en pratique ;
                # un plancher de 0,05 but évite log(0) sans changer une valeur réelle.
                frame[f"z_log_{column}"] = np.log(np.maximum(rows[column].astype(float), 0.05))
        if "G3" in self.groups:
            for side in ("", "opp_"):
                frame[f"z_{side}rest_days"] = np.minimum(rows[f"{side}rest_days"].astype(float), REST_CAP_DAYS)
                frame[f"z_{side}matches_last_14d"] = rows[f"{side}matches_last_14d"].astype(float)
                frame[f"{side}european_match_last_4d"] = rows[f"{side}european_match_last_4d"].astype(float)
        if "G4" in self.groups:
            for side in ("", "opp_"):
                frame[f"z_{side}coach_tenure_days"] = rows[f"{side}coach_tenure_days"].astype(float)
                frame[f"{side}coach_is_new"] = rows[f"{side}coach_is_new"].astype(float)
        if "G5" in self.groups:
            for column in G5_COLUMNS:
                frame[f"z_{column}"] = rows[column].astype(float)
        if "G6" in self.groups:
            for column in g6_columns(self.cohesion):
                frame[f"z_{column}"] = rows[column].astype(float)
        return frame

    def _league(self, rows: pd.DataFrame) -> pd.Series:
        return (rows["home_api_league_id"] if self.level == "match" else rows["api_league_id"]).astype(int)

    def fit(self, rows: pd.DataFrame) -> Design:
        """Apprend les modalités de championnat et la standardisation sur les seules lignes d'apprentissage."""
        self.leagues_ = sorted(self._league(rows).unique().tolist())
        raw = self._raw(rows)
        self.scale_ = {
            c: (float(raw[c].mean()), float(raw[c].std(ddof=0)) or 1.0) for c in raw.columns if c.startswith("z_")
        }
        # Une colonne constante dans l'apprentissage n'est pas estimable (matrice singulière) : on la retire,
        # et le retrait est écrit dans la description du modèle.
        self.dropped_ = [c for c in raw.columns if raw[c].nunique(dropna=False) <= 1]
        return self

    def transform(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Matrice (constante, indicatrices de championnat, variables standardisées)."""
        if not self.leagues_:
            raise RuntimeError("Design.fit doit précéder transform (standardisation apprise dans le pli).")
        raw = self._raw(rows)
        for column, (mean, std) in self.scale_.items():
            raw[column] = (raw[column] - mean) / std
        league = self._league(rows)
        unknown = set(league.unique()) - set(self.leagues_)
        if unknown:
            raise ValueError(f"Championnat(s) absent(s) de l'apprentissage : {sorted(unknown)}")
        dummies = pd.DataFrame(
            {f"league_{lg}": (league == lg).astype(float) for lg in self.leagues_[1:]}, index=rows.index
        )
        raw = raw.drop(columns=self.dropped_)
        return pd.concat([pd.Series(1.0, index=rows.index, name="const"), dummies, raw], axis=1)

    def fit_transform(self, rows: pd.DataFrame) -> pd.DataFrame:
        return self.fit(rows).transform(rows)

    def describe(self) -> dict:
        description = {"groups": list(self.groups), "half_life": self.half_life, "level": self.level}
        if self.cohesion is not None:
            description["cohesion"] = self.cohesion
        if self.first_training_season is not None:
            description["first_training_season"] = self.first_training_season
        return description | {"dropped": self.dropped_}
