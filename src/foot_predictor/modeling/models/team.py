"""M3 et M4 : modèles **par équipe** (rapport I.2, I.4 ; ADR-0009).

**M3, Poisson par équipe.** Une ligne par (match m, équipe e) : Y_{m,e} ~ Poisson(λ_{m,e}),
log λ_{m,e} = x_{m,e}ᵀ β, où x contient les variables de l'équipe **et** de son adversaire
(attaque de l'une contre défense de l'autre, sous forme additive grâce au lien log). Les deux
lignes d'un match partagent le même match : leurs erreurs sont corrélées, d'où des erreurs
standard **groupées par match** (sandwich par grappes). Les λ domicile et extérieur viennent des
deux lignes du match ; si Y_dom et Y_ext sont indépendants conditionnellement aux variables,
T = Y_dom + Y_ext ~ Poisson(λ_dom + λ_ext) (convolution), et la loi jointe donne score exact et 1N2.

Pourquoi décomposer (rapport I.2) : log(λ_dom + λ_ext) n'est pas linéaire dans les forces des
équipes ; un modèle du total (M2) mélange l'attaque d'une équipe et la défense de l'autre.

**M4, binomiale négative par équipe (NB2).** Même moyenne, variance μ + α μ² : α > 0 absorbe une
surdispersion. On ne la retient que si le test de Cameron-Trivedi **et** le rapport de
vraisemblance Poisson contre NB2 (au bord, ½ χ²₁) la justifient ; sinon, constat chiffré (une
fois les variables incluses, la dispersion est souvent ≈ 1, voire < 1).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm

from foot_predictor.modeling import diagnostics
from foot_predictor.modeling import distributions as dist
from foot_predictor.modeling.design import Design
from foot_predictor.modeling.models.base import MatchPredictions, Model, match_frame


def _pair(rows: pd.DataFrame, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(match_id, valeur domicile, valeur extérieur) à partir d'une valeur par ligne (match, équipe)."""
    matches = match_frame(rows[["match_id", "is_home"]].assign(value=values))
    return matches.index.to_numpy(), matches["home_value"].to_numpy(), matches["away_value"].to_numpy()


class M3(Model):
    """GLM de Poisson par équipe, erreurs standard groupées par match."""

    name = "M3"

    def __init__(self, groups=("G0", "G1"), half_life: int | None = None, check_dispersion: bool = False) -> None:
        super().__init__(groups=list(groups), half_life=half_life, check_dispersion=check_dispersion)
        self.check_dispersion = check_dispersion
        self.design = Design(tuple(groups), half_life, level="team")
        self.features = tuple(self.design.required())

    def fit(self, rows: pd.DataFrame) -> M3:
        X = self.design.fit_transform(rows)
        y = rows["goals_for"].to_numpy(dtype=float)
        clusters = pd.factorize(rows["match_id"])[0]
        model = sm.GLM(y, X, family=sm.families.Poisson())
        self.result_ = model.fit(cov_type="cluster", cov_kwds={"groups": clusters})
        naive = model.fit()  # mêmes coefficients, erreurs standard « naïves » (lignes indépendantes)
        mu = self.result_.fittedvalues.to_numpy()
        self.diagnostics_ = {
            "n_rows": int(len(y)),
            "n_matches": int(clusters.max() + 1),
            "loglik": float(self.result_.llf),
            "deviance": float(self.result_.deviance),
            "pearson_dispersion": diagnostics.pearson_dispersion(y, mu, X.shape[1]),
            "cameron_trivedi": diagnostics.cameron_trivedi(y, mu),
            "coefficients": {k: float(v) for k, v in self.result_.params.items()},
            "std_errors_cluster": {k: float(v) for k, v in self.result_.bse.items()},
            "std_errors_naive": {k: float(v) for k, v in naive.bse.items()},
            "design": self.design.describe(),
        }
        if self.check_dispersion:
            # Diagnostic de M4 sur l'apprentissage du pli : la binomiale négative n'est évaluée sur les plis
            # que si Cameron-Trivedi et le rapport de vraisemblance la justifient (sous-étape 4.8).
            nb = M4(self.design.groups, self.design.half_life).fit(rows).diagnostics_
            self.diagnostics_["negative_binomial"] = {k: nb[k] for k in ("alpha", "likelihood_ratio", "converged")}
        return self

    def team_lambda(self, rows: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.result_.predict(self.design.transform(rows)))

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        ids, lambda_home, lambda_away = _pair(rows, self.team_lambda(rows))
        return MatchPredictions.independent_poisson(ids, lambda_home, lambda_away)

    def describe(self) -> dict:
        return super().describe() | {"diagnostics": getattr(self, "diagnostics_", {})}


class M4(Model):
    """Binomiale négative NB2 par équipe : Var(Y) = μ + α μ², α estimé par maximum de vraisemblance."""

    name = "M4"

    def __init__(self, groups=("G0", "G1"), half_life: int | None = None) -> None:
        super().__init__(groups=list(groups), half_life=half_life)
        self.design = Design(tuple(groups), half_life, level="team")
        self.features = tuple(self.design.required())

    def fit(self, rows: pd.DataFrame) -> M4:
        X = self.design.fit_transform(rows)
        y = rows["goals_for"].to_numpy(dtype=float)
        poisson = sm.GLM(y, X, family=sm.families.Poisson()).fit()
        start = np.append(poisson.params.to_numpy(), 0.05)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # α proche de 0 : avertissements de convergence attendus au bord
            self.result_ = sm.NegativeBinomial(y, X, loglike_method="nb2").fit(
                start_params=start, method="bfgs", maxiter=500, disp=False
            )
        self.alpha_ = max(float(self.result_.params.iloc[-1]), 1e-8)
        self.beta_ = self.result_.params.iloc[:-1].to_numpy()
        self.diagnostics_ = {
            "n_rows": int(len(y)),
            "alpha": float(self.result_.params.iloc[-1]),
            "loglik_nb": float(self.result_.llf),
            "loglik_poisson": float(poisson.llf),
            "likelihood_ratio": diagnostics.likelihood_ratio_boundary(poisson.llf, self.result_.llf),
            "converged": bool(self.result_.mle_retvals.get("converged", False)),
            "design": self.design.describe(),
        }
        return self

    def predict(self, rows: pd.DataFrame) -> MatchPredictions:
        mu = np.exp(self.design.transform(rows).to_numpy() @ self.beta_)
        ids, mu_home, mu_away = _pair(rows, mu)
        home, away = dist.negbin_pmf(mu_home, self.alpha_), dist.negbin_pmf(mu_away, self.alpha_)
        total = dist.total_from_independent(home, away)
        joint = dist.independent_joint(dist.fold(home), dist.fold(away))
        return MatchPredictions(ids, mu_home, mu_away, total, home, away, joint)

    def describe(self) -> dict:
        return super().describe() | {"diagnostics": getattr(self, "diagnostics_", {})}
