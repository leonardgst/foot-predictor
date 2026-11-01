"""Évaluation du journal prospectif H1 (`python -m foot_predictor.inference prospective`, ADR-0052).

Le journal est `ops.prediction` : les prédictions live de l'horizon H1, écrites **avant** le coup d'envoi
(ADR-0011, règle 6). Cette commande les compare aux résultats réels, une fois ceux-ci connus de football-data
(superposition en mémoire, ADR-0042), et publie un relevé **descriptif** :

- décomptes de traçage : prédictions, écrites avant le coup d'envoi, jours de matchs (une journée = un jour
  avec au moins une prédiction tracée ; E.2 en demande au moins 8), résultats connus ou absents ;
- log-loss du total, RPS, Brier de P(T > 2,5), couverture observée de [q10 ; q90] contre l'annoncée, pente et
  ordonnée de calibration (descriptives, effectif petit) ;
- écart apparié à B1 (fenêtre 3, celle du test scellé), recalculé sur l'historique connu la veille de chaque
  jour, avec son intervalle par blocs de jours (protocole de l'ADR-0037).

Règle de lecture, fixée avant tout résultat : aucune règle de décision, aucun modèle changé, réentraîné ou
recalibré à partir de ce relevé ; aucune conclusion de performance avant 8 journées (seulement les décomptes).
Le rapport ne contient que des agrégats : ni score ni prédiction d'un match.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import TOP5
from foot_predictor.modeling import bootstrap, metrics
from foot_predictor.modeling.distributions import poisson_total

JOURNEES_REQUIRED = 8
"""Critère E.2 : prédictions live tracées avant le coup d'envoi pendant au moins 8 journées."""
N_RESAMPLES = 10_000
SEED = 20260930
B1_WINDOW = 3
"""Fenêtre de B1 retenue au test scellé (`scelle_h1.yaml`, `scelle_h2.yaml`)."""
N_CATEGORIES = 11
"""Cases de la loi du total : 0 à 9, « 10 et plus » (même grille que les réponses de l'inférence)."""


def journal_rows(session) -> list[dict]:
    """Prédictions live H1 disponibles de `ops.prediction` (le journal prospectif), dans l'ordre d'écriture."""
    from sqlalchemy import select

    from foot_predictor.db.models import Prediction

    query = (
        select(Prediction)
        .where(Prediction.mode == "live", Prediction.horizon == "H1", Prediction.status == "available")
        .order_by(Prediction.created_at, Prediction.id)
    )
    return [
        {
            "match_id": row.match_id,
            "api_fixture_id": row.api_fixture_id,
            "match_day": row.match_day,
            "kickoff_utc": row.kickoff_utc,
            "created_at": row.created_at,
            "model_version": row.model_version,
            "total_distribution": row.total_distribution,
        }
        for row in session.scalars(query)
    ]


def prediction_frame(rows: list[dict]) -> pd.DataFrame:
    """Prédictions du journal sous forme de table : une ligne par prédiction, loi du total en colonnes `p0` à `p10`."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    labels = [str(k) for k in range(N_CATEGORIES - 1)] + ["10+"]
    for k, label in enumerate(labels):
        frame[f"p{k}"] = [float(d[label]) for d in frame["total_distribution"]]
    frame["kickoff_utc"] = pd.to_datetime(frame["kickoff_utc"], utc=True)
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    frame["match_day"] = pd.to_datetime(frame["match_day"]).dt.date
    return frame


def tracing(frame: pd.DataFrame) -> dict:
    """Décomptes de traçage : prédictions, écrites avant le coup d'envoi, jours de matchs."""
    if frame.empty:
        return {"predictions": 0, "before_kickoff": 0, "after_or_unknown": 0, "journees": 0, "days": {}}
    before = frame["created_at"] < frame["kickoff_utc"]  # un coup d'envoi inconnu (vide) ne compte pas comme avant
    days = frame[before].groupby("match_day").size()
    return {
        "predictions": int(len(frame)),
        "before_kickoff": int(before.sum()),
        "after_or_unknown": int((~before).sum()),
        "journees": int(len(days)),
        "days": {d.isoformat(): int(n) for d, n in days.items()},
    }


def attach_results(frame: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Ajoute `total` (buts à 90 minutes) aux prédictions dont le match est joué ; les autres restent vides.

    Appariement par identifiant API du match, sinon par identifiant interne (`match_id`, stable dans un même
    chargement de `staging`, E-058). Aucun résultat n'est deviné.
    """
    played = matches[
        (matches["status"] == "played") & matches["home_goals_90"].notna() & matches["away_goals_90"].notna()
    ]
    total = (played["home_goals_90"].astype(float) + played["away_goals_90"].astype(float)).rename("total")
    by_match = pd.Series(total.to_numpy(), index=played["match_id"].astype(int).to_numpy())
    fixtures = played[played["api_fixture_id"].notna()]
    by_fixture = pd.Series(
        total.loc[fixtures.index].to_numpy(), index=fixtures["api_fixture_id"].astype(int).to_numpy()
    )
    out = frame.copy()
    from_fixture = out["api_fixture_id"].map(lambda v: by_fixture.get(int(v)) if pd.notna(v) else np.nan)
    from_match = out["match_id"].map(lambda v: by_match.get(int(v), np.nan))
    out["total"] = from_fixture.where(from_fixture.notna(), from_match).astype(float)
    return out


def b1_lambdas(matches: pd.DataFrame, frame: pd.DataFrame, window: int = B1_WINDOW) -> pd.DataFrame:
    """λ domicile et extérieur de B1 pour chaque prédiction, d'après l'historique connu **avant** son jour.

    B1 : moyenne de buts par championnat et par côté, sur les `window` dernières saisons (la saison en cours
    compte), matchs de championnat joués du top 5. Refait pour chaque jour de match.
    """
    history = matches[
        (matches["status"] == "played")
        & matches["is_regular_season"]
        & matches["api_league_id"].isin(list(TOP5))
        & matches["home_goals_90"].notna()
    ]
    league_of = matches.set_index("match_id")["api_league_id"]
    out = pd.DataFrame(index=frame.index, columns=["lambda_home", "lambda_away"], dtype=float)
    for day, part in frame.groupby("match_day"):
        known = history[history["match_day"] < day]
        if known.empty:
            continue
        last = int(known["season_year"].max())
        recent = known[known["season_year"] > last - window]
        means = recent.groupby("api_league_id")[["home_goals_90", "away_goals_90"]].mean()
        leagues = league_of.reindex(part["match_id"].to_numpy()).to_numpy()
        for index, league in zip(part.index, leagues, strict=True):
            if league in means.index:
                out.loc[index, "lambda_home"] = means.loc[league, "home_goals_90"]
                out.loc[index, "lambda_away"] = means.loc[league, "away_goals_90"]
    return out


def b1_distribution(lambdas: pd.DataFrame) -> np.ndarray:
    """Loi du total de B1 (Poisson indépendants : total Poisson(λ_dom + λ_ext)), repliée sur 11 cases."""
    total = poisson_total(lambdas["lambda_home"].to_numpy(float), lambdas["lambda_away"].to_numpy(float))
    return metrics.collapse(np.atleast_2d(total), N_CATEGORIES)


def scores(frame: pd.DataFrame) -> dict:
    """Mesures descriptives sur les prédictions dont le résultat est connu."""
    if frame.empty:
        return {"n": 0}
    probs = frame[[f"p{k}" for k in range(N_CATEGORIES)]].to_numpy(float)
    totals = frame["total"].to_numpy(float)
    over = metrics.prob_over(probs)
    outcome = totals > 2.5
    intercept, slope = (
        metrics.calibration_slope_intercept(over, outcome) if 0 < outcome.sum() < len(outcome) else (np.nan, np.nan)
    )
    return {
        "n": int(len(frame)),
        "log_loss": float(metrics.log_loss_by_match(probs, totals).mean()),
        "rps": float(metrics.rps_by_match(probs, totals).mean()),
        "brier_over_2_5": float(metrics.brier_over_by_match(probs, totals).mean()),
        "coverage": metrics.coverage(probs, totals),
        "mean_predicted_over_2_5": float(over.mean()),
        "observed_over_2_5": float(outcome.mean()),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
    }


def paired_with_b1(frame: pd.DataFrame, b1_probs: np.ndarray) -> dict:
    """Écart apparié `B1 − modèle` du log-loss (positif : le modèle fait mieux), intervalle par blocs de jours."""
    probs = frame[[f"p{k}" for k in range(N_CATEGORIES)]].to_numpy(float)
    totals = frame["total"].to_numpy(float)
    diff = metrics.log_loss_by_match(b1_probs, totals) - metrics.log_loss_by_match(probs, totals)
    blocks = frame["match_day"].astype(str).to_numpy()
    interval = bootstrap.block_bootstrap(diff, blocks, n_resamples=N_RESAMPLES, seed=SEED)
    return {
        "n": int(len(diff)),
        "log_loss_b1": float(metrics.log_loss_by_match(b1_probs, totals).mean()),
        "difference": interval.to_dict(),
        "diebold_mariano": bootstrap.diebold_mariano(diff, blocks),
    }


def evaluate(prediction_rows: list[dict], matches: pd.DataFrame, today: dt.date) -> dict:
    """Relevé complet : traçage, résultats connus, mesures, écart à B1. Agrégats seulement."""
    frame = prediction_frame(prediction_rows)
    trace = tracing(frame)
    report: dict = {
        "date": today.isoformat(),
        "journees_required": JOURNEES_REQUIRED,
        "tracing": trace,
        "enough_journees": trace["journees"] >= JOURNEES_REQUIRED,
        "model_versions": sorted(frame["model_version"].unique()) if not frame.empty else [],
    }
    if frame.empty:
        return report | {
            "with_result": 0,
            "without_result": 0,
            "scores": {"n": 0},
            "b1": None,
            "conclusion_allowed": False,
        }
    traced = frame[frame["created_at"] < frame["kickoff_utc"]]
    with_totals = attach_results(traced, matches)
    known = with_totals[with_totals["total"].notna()]
    report["with_result"] = int(len(known))
    report["without_result"] = int(len(with_totals) - len(known))
    report["scores"] = scores(known)
    report["b1"] = None
    if len(known) > 0:
        lambdas = b1_lambdas(matches, known)
        usable = known[lambdas["lambda_home"].notna().to_numpy()]
        if len(usable) > 0:
            report["b1"] = paired_with_b1(usable, b1_distribution(lambdas.loc[usable.index]))
            report["b1"]["without_b1"] = int(len(known) - len(usable))
    # Aucune conclusion de performance avant 8 journées : le rapport le dit, les chiffres restent descriptifs.
    report["conclusion_allowed"] = report["enough_journees"]
    return report


def render(report: dict) -> str:
    trace = report["tracing"]
    lines = [
        f"# Journal prospectif H1 — relevé du {report['date']}",
        "",
        "Produit par `python -m foot_predictor.inference prospective` (ADR-0052). **Relevé descriptif** : aucune "
        "règle de décision, aucun modèle changé à partir de ce relevé. Agrégats seulement.",
        "",
        "## Traçage (critère E.2)",
        "",
        f"- Modèle(s) : {', '.join(f'`{v}`' for v in report['model_versions']) or 'aucun'}.",
        f"- Prédictions dans le journal : {trace['predictions']}, dont **{trace['before_kickoff']} écrites avant le "
        f"coup d'envoi** ({trace['after_or_unknown']} après ou sans heure de coup d'envoi, écartées).",
        f"- **Journées tracées : {trace['journees']}** sur {report['journees_required']} demandées "
        f"({'atteint' if report['enough_journees'] else 'pas encore atteint'}).",
        "",
        "| Jour | Prédictions |",
        "|---|---|",
    ]
    lines += [f"| {day} | {n} |" for day, n in trace["days"].items()]
    lines += [
        "",
        "## Résultats connus",
        "",
        f"- Prédictions avec résultat connu : {report.get('with_result', 0)} ; sans résultat (match pas joué, ou "
        f"résultat absent de football-data) : {report.get('without_result', 0)}.",
    ]
    score = report.get("scores", {})
    if score.get("n"):
        cov = score["coverage"]
        lines += [
            "",
            "## Mesures"
            + ("" if report["conclusion_allowed"] else " (descriptives : moins de 8 journées, aucune conclusion)"),
            "",
            "| Mesure | Valeur |",
            "|---|---|",
            f"| Matchs | {score['n']} |",
            f"| Log-loss du total | {score['log_loss']:.4f} |",
            f"| RPS | {score['rps']:.4f} |",
            f"| Brier de P(T > 2,5) | {score['brier_over_2_5']:.4f} |",
            f"| P(T > 2,5) : prédite en moyenne / observée | {score['mean_predicted_over_2_5']:.3f} / "
            f"{score['observed_over_2_5']:.3f} |",
            f"| Couverture de [q10 ; q90] : observée / annoncée | {cov['observed']:.1%} / {cov['announced']:.1%} |",
            f"| Calibration (ordonnée, pente) | {score['calibration_intercept']:.2f}, {score['calibration_slope']:.2f} |",
        ]
    b1 = report.get("b1")
    if b1:
        interval = b1["difference"]
        lines += [
            "",
            "## Écart à B1 (fenêtre 3)",
            "",
            f"Écart apparié `B1 − modèle` du log-loss (positif : le modèle fait mieux), {b1['n']} matchs, "
            f"{interval['n_blocks']} jours, {N_RESAMPLES} rééchantillonnages, graine {SEED} :",
            "",
            f"**{interval['mean']:+.4f} [{interval['low']:+.4f} ; {interval['high']:+.4f}]** "
            f"(Diebold-Mariano p = {b1['diebold_mariano']['p_value']:.3f}).",
            f"Log-loss de B1 : {b1['log_loss_b1']:.4f}. Sans B1 (championnat absent de l'historique) : "
            f"{b1.get('without_b1', 0)}.",
        ]
    if report["conclusion_allowed"]:
        reading = (
            "Les 8 journées sont atteintes : le relevé se lit avec son intervalle, sans règle de décision ni "
            "changement de modèle (ADR-0052)."
        )
    else:
        reading = (
            "Avec moins de 8 journées et quelques dizaines de matchs, l'intervalle est large : le relevé décrit, "
            "il ne tranche pas."
        )
    lines += [
        "",
        "## Lecture",
        "",
        reading + " Il est refait à chaque collecte de résultats ; tous les relevés sont conservés.",
    ]
    return "\n".join(lines) + "\n"
