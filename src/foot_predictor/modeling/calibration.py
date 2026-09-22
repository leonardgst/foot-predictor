"""Recalibration post-hoc des probabilités du Modèle A (Poisson indépendant) --
cf. `docs/RESULTATS_MODELE.md` section 5.

Contexte : la table de calibration `evaluation.calibration_table_home_win`
montre une légère sur-confiance du Modèle A dans les tranches médianes-hautes
de probabilité de victoire à domicile (ex. 30-40 % prédit vs ~29.7 % observé,
70-80 % prédit vs ~68.5 % observé). Ce module fournit deux méthodes de
recalibration standard, ajustées **hors du test set** (cf.
`run_calibration_analysis.py` pour le protocole anti-fuite, même esprit que
`run_comparison.py::_select_xi`) :

- Platt scaling : régression logistique 1D sur la probabilité prédite --
  `sklearn.linear_model.LogisticRegression`.
- Isotonic regression : régression isotone (fonction monotone non paramétrique)
  -- `sklearn.isotonic.IsotonicRegression`.

Simplification documentée (cf. `docs/RESULTATS_MODELE.md` section 5, point sur
la méthodologie) : les deux méthodes ci-dessus recalibrent un scalaire
`P(classe)` contre `1 - P(classe)`, donc ne préservent pas nativement
`P(domicile) + P(nul) + P(extérieur) = 1` pour les 3 issues du marché 1N2.
L'approche retenue ici est "one-vs-rest puis renormalisation" :
`calibrate_ovr_and_renormalize` recalibre indépendamment chacune des 3
probabilités (une par classe, chacune vue comme un problème binaire "cette
classe est-elle la bonne ?"), puis renormalise les 3 valeurs recalibrées pour
qu'elles resomment à 1. C'est une approximation -- une méthode de calibration
multi-classe rigoureuse (ex. calibration de Dirichlet) n'est pas implémentée
ici, hors scope de cette passe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

Method = Literal["platt", "isotonic"]


class Calibrator(Protocol):
    """Interface commune aux deux calibrateurs : un vecteur de probabilités
    prédites en entrée, un vecteur de probabilités recalibrées en sortie."""

    def predict(self, p_pred: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class PlattCalibrator:
    model: LogisticRegression

    def predict(self, p_pred: np.ndarray) -> np.ndarray:
        p = np.asarray(p_pred, dtype=float).reshape(-1, 1)
        return self.model.predict_proba(p)[:, 1]


@dataclass(frozen=True)
class IsotonicCalibrator:
    model: IsotonicRegression

    def predict(self, p_pred: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict(np.asarray(p_pred, dtype=float)))


def fit_platt_calibrator(p_pred: np.ndarray, y_true: np.ndarray) -> PlattCalibrator:
    """Ajuste une régression logistique 1D : logit(P(y=1)) = a * p_pred + b.
    `y_true` doit contenir les deux classes (0 et 1) sur la fenêtre de fit --
    sinon `LogisticRegression` ne peut pas s'ajuster (ValueError explicite de
    sklearn, volontairement non masquée)."""
    p = np.asarray(p_pred, dtype=float).reshape(-1, 1)
    y = np.asarray(y_true, dtype=int)
    model = LogisticRegression()
    model.fit(p, y)
    return PlattCalibrator(model=model)


def fit_isotonic_calibrator(p_pred: np.ndarray, y_true: np.ndarray) -> IsotonicCalibrator:
    """Ajuste une régression isotone (monotone croissante) p_pred -> P(y=1)."""
    p = np.asarray(p_pred, dtype=float)
    y = np.asarray(y_true, dtype=int)
    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    model.fit(p, y)
    return IsotonicCalibrator(model=model)


FIT_FUNCTIONS = {"platt": fit_platt_calibrator, "isotonic": fit_isotonic_calibrator}


def fit_calibrator(method: Method, p_pred: np.ndarray, y_true: np.ndarray) -> Calibrator:
    """Point d'entrée générique -- délègue à `fit_platt_calibrator` ou
    `fit_isotonic_calibrator` selon `method`."""
    if method not in FIT_FUNCTIONS:
        raise ValueError(f"Méthode de calibration inconnue : {method!r} (attendu : 'platt' ou 'isotonic')")
    return FIT_FUNCTIONS[method](p_pred, y_true)


def apply_calibrator(calibrator: Calibrator, p_pred: np.ndarray) -> np.ndarray:
    return np.asarray(calibrator.predict(p_pred))


# --- Recalibration 3 classes (1N2) : one-vs-rest + renormalisation ----------

# Convention d'encodage de l'issue : 0 = victoire domicile, 1 = nul, 2 = victoire extérieur.
HOME, DRAW, AWAY = 0, 1, 2


def fit_ovr_calibrators(
    method: Method,
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
    y_outcome: np.ndarray,
) -> tuple[Calibrator, Calibrator, Calibrator]:
    """Ajuste un calibrateur indépendant par issue (one-vs-rest) : pour
    l'issue "domicile", la cible binaire est `y_outcome == HOME`, etc.
    `y_outcome` : un code par match parmi {HOME=0, DRAW=1, AWAY=2}."""
    y = np.asarray(y_outcome)
    cal_home = fit_calibrator(method, p_home, (y == HOME).astype(int))
    cal_draw = fit_calibrator(method, p_draw, (y == DRAW).astype(int))
    cal_away = fit_calibrator(method, p_away, (y == AWAY).astype(int))
    return cal_home, cal_draw, cal_away


def calibrate_ovr_and_renormalize(
    calibrators: tuple[Calibrator, Calibrator, Calibrator],
    p_home: np.ndarray,
    p_draw: np.ndarray,
    p_away: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Applique les 3 calibrateurs one-vs-rest puis renormalise pour que
    P(domicile) + P(nul) + P(extérieur) = 1 (cf. docstring du module --
    approximation documentée, pas une calibration multi-classe rigoureuse)."""
    cal_home, cal_draw, cal_away = calibrators
    p_home_c = apply_calibrator(cal_home, p_home)
    p_draw_c = apply_calibrator(cal_draw, p_draw)
    p_away_c = apply_calibrator(cal_away, p_away)

    total = p_home_c + p_draw_c + p_away_c
    # Garde-fou numérique : ne devrait se produire que si les 3 calibrateurs
    # renvoient (quasi) 0 simultanément, cas dégénéré non rencontré en pratique.
    total = np.where(total <= 1e-12, 1.0, total)
    return p_home_c / total, p_draw_c / total, p_away_c / total


# --- Métrique de calibration réutilisable (tests + script d'analyse) -------


def mean_absolute_calibration_error(p_pred: np.ndarray, y_true: np.ndarray, n_bins: int = 10) -> float:
    """Erreur de calibration moyenne absolue (ECE non pondérée par la taille
    des tranches) : découpe [0, 1] en `n_bins` tranches égales, calcule
    |probabilité prédite moyenne - fréquence observée| par tranche non vide,
    moyenne sur les tranches. Même logique de binning que
    `evaluation.calibration_table_home_win`, mais sur des tableaux nus (pas de
    dépendance à `MatchPredictions` / DB) pour rester testable en isolation."""
    import pandas as pd

    df = pd.DataFrame({"p_pred": np.asarray(p_pred, dtype=float), "actual": np.asarray(y_true, dtype=int)})
    df["bin"] = pd.cut(df["p_pred"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True)
    table = df.groupby("bin", observed=True).agg(
        mean_predicted=("p_pred", "mean"), observed_frequency=("actual", "mean")
    )
    if table.empty:
        return float("nan")
    return float((table["mean_predicted"] - table["observed_frequency"]).abs().mean())
