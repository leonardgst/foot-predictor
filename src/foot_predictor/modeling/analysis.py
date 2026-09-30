"""Analyses des ablations (sous-étape 4.12) : courbe d'apport, figure, analyses descriptives.

**Courbe d'apport** (rapport I.7) : gain cumulé de log-loss du total sur B0, étape par étape
(G0, puis + G1, + G2, + G3), avec son intervalle à 95 % ; et l'apport propre de chaque groupe
(écart avec l'étape précédente). Tous les chiffres viennent du rapport JSON de l'expérience.

**Analyses descriptives** (jamais pour sélectionner) sur les prédictions par match
(`data/experiments/<id>/predictions.parquet`) :

- gain par tranche de journées (début de saison, rapport H.4) ;
- gain par championnat et par format (Ligue 1 à 18 clubs depuis 2023-24) ;
- huis clos : aucun match à huis clos dans les saisons de test ; on lit donc les coefficients du
  domicile et de son interaction avec le huis clos, estimés dans chaque pli (erreurs groupées).

Les intervalles des analyses descriptives sont aussi des bootstraps par blocs de journées ; ils
ne comptent pas dans la règle de décision (ADR-0037).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.modeling import bootstrap, metrics
from foot_predictor.modeling.experiment import ROUND_BUCKETS, round_number

SERIES_COLOR = "#2a78d6"  # palette de référence, rang 1 (validée : contraste ≥ 3:1 sur #fcfcfb)
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"


def contribution_table(report: dict, reference: str, steps: list[tuple[str, str]]) -> pd.DataFrame:
    """Gain cumulé sur `reference` et apport de chaque étape, lus dans les comparaisons du rapport.

    `steps` : [(identifiant du modèle, libellé)], dans l'ordre d'ajout des groupes.
    """
    comparisons = {(c["a"], c["b"]): c for c in report["comparisons"] if "log_loss" in c}
    rows, previous = [], None
    for model, label in steps:
        cumulative = comparisons[(reference, model)]["log_loss"]["pooled"]
        row = {
            "model": model,
            "label": label,
            "cumulative": cumulative["mean"],
            "cumulative_low": cumulative["low"],
            "cumulative_high": cumulative["high"],
            "log_loss": report["pooled"][model]["log_loss"],
        }
        if previous is not None and (previous, model) in comparisons:
            step = comparisons[(previous, model)]
            row |= {
                "step": step["log_loss"]["pooled"]["mean"],
                "step_low": step["log_loss"]["pooled"]["low"],
                "step_high": step["log_loss"]["pooled"]["high"],
                "positive_folds": step["log_loss"]["positive_folds"],
                "retained": step["decision"]["b_replaces_a"],
            }
        rows.append(row)
        previous = model
    return pd.DataFrame(rows)


def plot_contribution(table: pd.DataFrame, path: Path, reference_label: str = "B0") -> Path:
    """Figure de la courbe d'apport : gain cumulé (points) et intervalle à 95 % (barres), PNG compact."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=110)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    x = np.arange(len(table))
    y = table["cumulative"].to_numpy()
    lower = y - table["cumulative_low"].to_numpy()
    upper = table["cumulative_high"].to_numpy() - y
    ax.axhline(0, color=TEXT_SECONDARY, linewidth=0.8)
    ax.plot(x, y, color=SERIES_COLOR, linewidth=2, zorder=2)
    ax.errorbar(x, y, yerr=[lower, upper], fmt="o", color=SERIES_COLOR, markersize=8, capsize=0,
                elinewidth=2, markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)  # fmt: skip
    for xi, yi, top in zip(x, y, table["cumulative_high"].to_numpy(), strict=True):
        ax.annotate(f"{yi:+.4f}".replace(".", ","), (xi, top), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=8, color=TEXT_PRIMARY)  # fmt: skip
    ax.set_xticks(x, table["label"], fontsize=8, color=TEXT_PRIMARY)
    ax.tick_params(axis="y", labelsize=8, colors=TEXT_SECONDARY)
    ax.set_ylabel(f"Gain de log-loss sur {reference_label}", fontsize=8, color=TEXT_SECONDARY)
    ax.set_title(
        "Courbe d'apport : gain cumulé par groupe (IC 95 %, 4 plis)", fontsize=9, color=TEXT_PRIMARY, loc="left"
    )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(TEXT_SECONDARY)
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.6)
    ax.set_ylim(top=float(table["cumulative_high"].max()) * 1.15)  # place pour les valeurs au-dessus des intervalles
    ax.set_axisbelow(True)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


# ------------------------------------------------------------------------------ analyses descriptives


def match_losses(predictions: pd.DataFrame, model: str) -> pd.Series:
    """Log-loss du total par match (index : match_id) d'un modèle, depuis le Parquet des prédictions."""
    part = predictions[predictions["model"] == model].set_index("match_id")
    probs = part[[c for c in part.columns if c.startswith("p_total_")]].to_numpy()
    return pd.Series(metrics.log_loss_by_match(probs, part["total"].to_numpy()), index=part.index)


def match_context(data: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par match du jeu : championnat, saison, journée (numéro), date, bloc du bootstrap."""
    home = data[data["is_home"]].set_index("match_id")
    context = home[["api_league_id", "season_year", "round", "match_day"]].copy()
    context["round_number"] = round_number(context["round"])
    context["block"] = bootstrap.block_keys(context)
    return context


def gain_by_group(
    predictions: pd.DataFrame, data: pd.DataFrame, a: str, b: str, group: pd.Series, seed: int, n_resamples: int
) -> pd.DataFrame:
    """Gain moyen A − B par modalité de `group` (indexé par match_id), avec intervalle par blocs."""
    diff = (match_losses(predictions, a) - match_losses(predictions, b)).dropna()
    context = match_context(data).loc[diff.index]
    labels = group.loc[diff.index]
    rows = []

    def order(label):  # « 6-10 » avant « 11-19 » : tri numérique quand le libellé commence par un nombre
        head = str(label).split("-")[0]
        return (0, int(head), "") if head.isdigit() else (1, 0, str(label))

    for label in sorted(labels.dropna().unique(), key=order):
        mask = (labels == label).to_numpy()
        interval = bootstrap.block_bootstrap(
            diff.to_numpy()[mask], context["block"].to_numpy()[mask], n_resamples=n_resamples, seed=seed
        )
        rows.append({"group": label, **interval.to_dict()})
    return pd.DataFrame(rows)


def round_bucket(context: pd.DataFrame) -> pd.Series:
    """Tranche de journées (1-5, 6-10, 11-19, 20-99) de chaque match."""
    labels = pd.Series(pd.NA, index=context.index, dtype="object")
    for lo, hi in ROUND_BUCKETS:
        labels[(context["round_number"] >= lo) & (context["round_number"] <= hi)] = f"{lo}-{hi}"
    return labels


def league_format(context: pd.DataFrame) -> pd.Series:
    """Championnat, en séparant la Ligue 1 à 20 clubs (jusqu'en 2022-23) et à 18 clubs (depuis 2023-24)."""
    names = {39: "Premier League", 140: "La Liga", 78: "Bundesliga", 135: "Serie A", 61: "Ligue 1"}
    labels = context["api_league_id"].map(names).astype("object")
    ligue1 = context["api_league_id"] == 61
    labels[ligue1 & (context["season_year"] >= 2023)] = "Ligue 1, 18 clubs"
    labels[ligue1 & (context["season_year"] < 2023)] = "Ligue 1, 20 clubs"
    return labels


def closed_doors_effect(report: dict, model: str) -> pd.DataFrame:
    """Coefficients domicile et domicile × huis clos de chaque pli, avec intervalle à 95 % (erreurs groupées)."""
    rows = []
    for fold in report["folds"]:
        diag = fold["models"][model]["fitted"]["diagnostics"]
        coef, se = diag["coefficients"], diag["std_errors_cluster"]
        if "home_x_closed" not in coef:
            continue
        home, inter = coef["is_home"], coef["home_x_closed"]
        rows.append(
            {
                "fold": fold["name"],
                "home": home,
                "home_x_closed": inter,
                "home_x_closed_low": inter - 1.96 * se["home_x_closed"],
                "home_x_closed_high": inter + 1.96 * se["home_x_closed"],
                "home_ratio_open": float(np.exp(home)),
                "home_ratio_closed": float(np.exp(home + inter)),
            }
        )
    return pd.DataFrame(rows)
