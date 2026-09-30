"""Inférence sur les écarts de perte : bootstrap par blocs et test de Diebold-Mariano (ADR-0037).

On compare deux modèles A et B **sur les mêmes matchs** : pour chaque match i, d_i = perte_A(i)
− perte_B(i) (positif : B fait mieux). Les matchs d'une même journée d'un championnat sont
corrélés (mêmes conditions, même calendrier) : on rééchantillonne donc des **blocs** entiers,
jamais des matchs isolés.

- **Bloc** (décision 7) : (championnat, saison, journée), la journée étant `round`
  d'API-FOOTBALL ; à défaut de `round`, (championnat, semaine ISO).
- **Bootstrap stratifié par pli** : dans chaque pli, on tire avec remise autant de blocs qu'il
  en a ; la moyenne poolée est Σ sommes des blocs tirés / Σ effectifs des blocs tirés. Le calcul
  se fait par **sommes par bloc** (rapide) : aucun modèle n'est réajusté.
- **Intervalle à 95 %** : percentiles 2,5 et 97,5 des moyennes rééchantillonnées ; 10 000
  rééchantillonnages, graine fixe (écrite dans le fichier d'expérience).
- **Diebold-Mariano** : DM = d̄ / √V̂(d̄), où V̂ est la variance groupée par bloc,
  V̂ = Σ_b (S_b − n_b d̄)² / N² (sandwich par grappes, l'équivalent d'une correction HAC par
  journée). Sous l'hypothèse « même perte attendue », DM suit approximativement N(0, 1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

N_RESAMPLES = 10_000
LEVEL = 0.95


def block_keys(frame: pd.DataFrame) -> pd.Series:
    """Clé de bloc de chaque match : `ligue:saison:journée`, sinon `ligue:année-Wsemaine` (ISO).

    Colonnes lues : `api_league_id`, `season_year`, `round`, `match_day` (date du match).
    """
    day = pd.to_datetime(frame["match_day"])
    iso = day.dt.isocalendar()
    week = frame["api_league_id"].astype(str) + ":" + iso["year"].astype(str) + "-W" + iso["week"].astype(str)
    has_round = frame["round"].notna() if "round" in frame.columns else pd.Series(False, index=frame.index)
    by_round = (
        frame["api_league_id"].astype(str) + ":" + frame["season_year"].astype(str) + ":" + frame["round"].astype(str)
        if "round" in frame.columns
        else week
    )
    return pd.Series(np.where(has_round, by_round, week), index=frame.index)


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float
    n: int
    n_blocks: int

    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0

    def to_dict(self) -> dict:
        return {"mean": self.mean, "low": self.low, "high": self.high, "n": self.n, "n_blocks": self.n_blocks}


def _block_sums(diff: np.ndarray, blocks: np.ndarray, strata: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame = pd.DataFrame({"d": diff, "b": blocks, "s": strata})
    grouped = frame.groupby(["s", "b"], sort=True)["d"].agg(["sum", "size"]).reset_index()
    return grouped["sum"].to_numpy(), grouped["size"].to_numpy(), grouped["s"].to_numpy()


def block_bootstrap(
    diff, blocks, strata=None, n_resamples: int = N_RESAMPLES, seed: int = 0, level: float = LEVEL
) -> Interval:
    """Intervalle de la moyenne de `diff` par bootstrap de blocs, stratifié par `strata` (le pli).

    Déterministe : même graine, même intervalle.
    """
    diff = np.asarray(diff, dtype=float)
    blocks = np.asarray(blocks)
    strata = np.zeros(len(diff), dtype=int) if strata is None else np.asarray(strata)
    if np.isnan(diff).any():
        raise ValueError("Écart de perte vide : les matchs comparés doivent être les mêmes (intersection).")
    sums, sizes, block_strata = _block_sums(diff, blocks, strata)
    rng = np.random.default_rng(seed)
    total_sum = np.zeros(n_resamples)
    total_size = np.zeros(n_resamples)
    for stratum in np.unique(block_strata):
        index = np.flatnonzero(block_strata == stratum)
        draws = index[rng.integers(0, len(index), size=(n_resamples, len(index)))]
        total_sum += sums[draws].sum(axis=1)
        total_size += sizes[draws].sum(axis=1)
    means = total_sum / total_size
    alpha = (1 - level) / 2
    low, high = np.quantile(means, [alpha, 1 - alpha])
    return Interval(float(diff.mean()), float(low), float(high), int(len(diff)), int(len(sums)))


def diebold_mariano(diff, blocks) -> dict:
    """Statistique de Diebold-Mariano à variance groupée par bloc, et sa p-valeur bilatérale."""
    diff = np.asarray(diff, dtype=float)
    frame = pd.DataFrame({"d": diff, "b": np.asarray(blocks)})
    grouped = frame.groupby("b")["d"].agg(["sum", "size"])
    n, mean = len(diff), diff.mean()
    variance = ((grouped["sum"] - grouped["size"] * mean) ** 2).sum() / n**2
    if variance <= 0:
        return {"statistic": float("nan"), "p_value": float("nan")}
    statistic = mean / np.sqrt(variance)
    return {"statistic": float(statistic), "p_value": float(2 * norm.sf(abs(statistic)))}
