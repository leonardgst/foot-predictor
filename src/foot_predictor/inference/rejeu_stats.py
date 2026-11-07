"""Statistiques du rejeu H1 sur toutes les saisons (`python -m foot_predictor.inference rejeu-stats`).

Rejoue chaque journée de championnat du top 5 depuis 2021-22 par la même fonction que l'API (`predict_day`,
mode rejeu, horizon H1 : modèle du pli de la saison, modèle du test scellé pour 2025-26 et 2026-27, score réel,
**aucune cote**), puis agrège :

- le total, par période (2021-22 à 2024-25, puis 2025-26 et 2026-27), par championnat, par saison et par
  saison × championnat : log-loss, RPS, Brier de P(T > 2,5), part de bons « plus/moins de 2,5 buts », buts
  prévus et observés, part de bons vainqueurs, écart apparié à B1 (fenêtre 3, comme le test scellé) ;
- l'évolution dans la saison : par tranche de journées, et par pente de l'erreur selon l'avancement de la saison
  (intervalles par rééchantillonnage de blocs de journées, graine et nombre de tirages du protocole, ADR-0037).

Règle de lecture, fixée avant tout résultat : relevé **descriptif**, aucune règle de décision, aucun modèle
changé à partir de lui. Les saisons 2021-22 à 2024-25 ont servi à choisir les modèles et les réglages : seules
2025-26 et 2026-27 n'y ont pas servi, et les deux blocs restent séparés. Les analyses sont nombreuses : un
intervalle qui exclut 0 dans l'une d'elles ne prouve rien seul (environ 5 % le font par hasard).

Le vainqueur le plus probable est déduit des deux moyennes de buts du modèle (Poissons indépendants) : le
protocole ne l'a pas validé, il est descriptif. Le rapport ne contient que des agrégats ; les prédictions match
par match (avec score réel) restent dans `data/inference/` (non suivi par Git).
"""

from __future__ import annotations

import datetime as dt
import re
import time
from collections import Counter

import numpy as np
import pandas as pd

from foot_predictor.features.leagues import TOP5
from foot_predictor.inference.prospective import N_CATEGORIES, N_RESAMPLES, SEED, b1_distribution, b1_lambdas
from foot_predictor.modeling import bootstrap, metrics
from foot_predictor.modeling.distributions import independent_joint, outcome_probabilities, poisson_pmf

FIRST_SEASON = 2021
"""Première saison rejouée : celle du premier pli de validation."""
COMPLETE_SHARE = 0.9
"""Une saison est terminée quand ses journées jouées atteignent cette part de son nombre de journées."""
MIN_BLOCKS = 5
"""Journées (blocs) minimales pour un intervalle : en dessous, le rééchantillonnage ne dit rien."""
FIRST_SEALED_SEASON = 2025
"""À partir de cette saison, les matchs sont ceux du test scellé (joués depuis le 1er juillet 2025)."""
TRANCHES = ((1, 5), (6, 10), (11, 19), (20, 29), (30, 99))
"""Tranches de journées : celles de `docs/resultats/ablations.md`, la dernière coupée en deux."""
FALLBACK_ROUNDS = {39: 38, 140: 38, 78: 34, 135: 38, 61: 34}
"""Journées d'une saison complète, quand la saison en cours n'a pas de saison précédente à copier."""
LEVEL = 0.95
MIN_TREND = 30
"""Effectif minimal pour estimer une pente."""
P_COLUMNS = [f"p{k}" for k in range(N_CATEGORIES)]
LABELS = [str(k) for k in range(N_CATEGORIES - 1)] + ["10+"]
PERIODS = (("validation", "2021-22 à 2024-25"), ("scelle", "2025-26 et 2026-27 (test scellé)"))

_ROUND = re.compile(r"(\d+)\s*$")


def season_label(season: int) -> str:
    return f"{season}-{str(season + 1)[2:]}"


def round_number(value) -> float:
    """Numéro de journée de « Regular Season - 12 » ; vide si le texte n'en porte pas."""
    if not isinstance(value, str):
        return np.nan
    found = _ROUND.search(value)
    return float(found.group(1)) if found else np.nan


# ------------------------------------------------------------------------------ collecte


def replay_scope(matches: pd.DataFrame, since_season: int = FIRST_SEASON) -> pd.DataFrame:
    """Matchs de championnat du top 5 joués, à partir de la saison `since_season`."""
    keep = (
        matches["api_league_id"].isin(list(TOP5))
        & matches["is_regular_season"]
        & (matches["status"] == "played")
        & (matches["season_year"] >= since_season)
    )
    return matches[keep]


def answers_frame(answers: list[dict]) -> tuple[pd.DataFrame, Counter]:
    """Réponses de `predict_day` → une ligne par match prédit avec son score réel ; le reste est compté."""
    rows, skipped = [], Counter()
    for answer in answers:
        prediction, score = answer.get("prediction"), answer.get("actual_score")
        if prediction is None:
            skipped[answer.get("status") or "sans_prediction"] += 1
            continue
        if not score or score.get("home") is None or score.get("away") is None:
            skipped["sans_score"] += 1
            continue
        distribution = prediction["total_distribution"]
        rows.append(
            {
                "match_id": answer["match_id"],
                "api_league_id": answer["api_league_id"],
                "competition": answer["competition"],
                "season_year": answer["season"],
                "round": answer["round"],
                "match_day": dt.date.fromisoformat(answer["date"]),
                "model_version": answer["model_version"],
                "lambda_home": prediction["lambda_home"],
                "lambda_away": prediction["lambda_away"],
                "home_goals": int(score["home"]),
                "away_goals": int(score["away"]),
                **{f"p{k}": float(distribution[label]) for k, label in enumerate(LABELS)},
            }
        )
    return pd.DataFrame(rows), skipped


def collect(context, since_season: int = FIRST_SEASON, predict=None, progress=None) -> tuple[pd.DataFrame, Counter]:
    """Rejoue chaque jour de match du périmètre ; renvoie les prédictions avec score réel et les exclusions."""
    if predict is None:
        from foot_predictor.inference.predict import predict_day as predict
    scope = replay_scope(context.matches, since_season)
    days = sorted(scope["match_day"].unique())
    competition_ids = sorted(int(c) for c in scope["competition_id"].unique())
    parts, excluded, start = [], Counter(), time.monotonic()
    for done, day in enumerate(days, start=1):
        part, skipped = answers_frame(predict(day, "replay", context, competition_ids, horizon="H1"))
        if not part.empty:
            parts.append(part)
        excluded.update(skipped)
        if progress is not None and (done % 25 == 0 or done == len(days)):
            progress(done, len(days), time.monotonic() - start)
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return frame, excluded


def add_b1(frame: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """λ de B1 (fenêtre 3) calculés sur l'historique connu la veille de chaque jour, comme au relevé prospectif."""
    lambdas = b1_lambdas(matches, frame)
    out = frame.copy()
    out["lambda_b1_home"] = lambdas["lambda_home"]
    out["lambda_b1_away"] = lambdas["lambda_away"]
    return out


# ------------------------------------------------------------------------------ mesures par match


def measures(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les mesures de chaque match : pertes, bons « plus/moins de 2,5 », vainqueur, écart à B1."""
    out = frame.copy()
    probs = out[P_COLUMNS].to_numpy(float)
    home, away = out["home_goals"].to_numpy(int), out["away_goals"].to_numpy(int)
    totals = (home + away).astype(float)
    out["total"] = totals
    out["log_loss"] = metrics.log_loss_by_match(probs, totals)
    out["rps"] = metrics.rps_by_match(probs, totals)
    out["p_over"] = metrics.prob_over(probs)
    out["over"] = totals > 2.5
    out["brier_over"] = metrics.brier_over_by_match(probs, totals)
    out["hit_over"] = (out["p_over"] > 0.5) == out["over"]
    out["expected_total"] = out["lambda_home"] + out["lambda_away"]
    # Vainqueur le plus probable : Poissons indépendants des deux moyennes de buts (structure de M3).
    joint = independent_joint(
        poisson_pmf(out["lambda_home"].to_numpy(float)), poisson_pmf(out["lambda_away"].to_numpy(float))
    )
    outcome = outcome_probabilities(joint)
    out["p_home"], out["p_draw"], out["p_away"] = outcome[:, 0], outcome[:, 1], outcome[:, 2]
    observed = np.where(home > away, 0, np.where(home == away, 1, 2))
    out["hit_1x2"] = outcome.argmax(axis=1) == observed
    out["brier_1x2"] = metrics.brier_1x2_by_match(outcome, home, away)
    log_loss_b1 = np.full(len(out), np.nan)
    if {"lambda_b1_home", "lambda_b1_away"} <= set(out.columns):
        valid = out[["lambda_b1_home", "lambda_b1_away"]].notna().all(axis=1).to_numpy()
        if valid.any():
            b1 = b1_distribution(
                pd.DataFrame(
                    {
                        "lambda_home": out.loc[valid, "lambda_b1_home"].to_numpy(float),
                        "lambda_away": out.loc[valid, "lambda_b1_away"].to_numpy(float),
                    }
                )
            )
            log_loss_b1[valid] = metrics.log_loss_by_match(b1, totals[valid])
    out["log_loss_b1"] = log_loss_b1
    out["delta_b1"] = out["log_loss_b1"] - out["log_loss"]  # positif : le modèle fait mieux que B1
    out["period"] = np.where(out["season_year"] >= FIRST_SEALED_SEASON, "scelle", "validation")
    return out


def add_progress(frame: pd.DataFrame) -> pd.DataFrame:
    """Avancement dans la saison (0 = journée 1, 1 = dernière journée) et tranche de journées.

    Le nombre de journées d'une saison est la plus grande journée observée ; pour la saison en cours, qui n'est
    pas finie, c'est celui de la saison précédente du championnat (sinon `FALLBACK_ROUNDS`).
    """
    out = frame.copy()
    out["round_no"] = out["round"].map(round_number)
    observed = out.groupby(["api_league_id", "season_year"])["round_no"].max().to_dict()
    n_rounds = dict(observed)
    for league in {league for league, _ in observed}:
        last = max(season for lg, season in observed if lg == league)
        reference = observed.get((league, last - 1), FALLBACK_ROUNDS.get(int(league), np.nan))
        current = observed[(league, last)]
        n_rounds[(league, last)] = current if np.isnan(reference) else max(current, reference)
    totals = np.array([n_rounds[(lg, s)] for lg, s in zip(out["api_league_id"], out["season_year"], strict=True)])
    out["n_rounds"] = totals
    played = out.groupby(["api_league_id", "season_year"])["round_no"].transform("max")
    out["season_complete"] = (played / totals) >= COMPLETE_SHARE
    with np.errstate(invalid="ignore", divide="ignore"):
        out["progress"] = ((out["round_no"] - 1) / (totals - 1)).clip(0, 1)
    order = [tranche_label(low) for low, _ in TRANCHES]
    out["tranche"] = pd.Categorical(out["round_no"].map(tranche_label), categories=order, ordered=True)
    return out


def tranche_label(round_no: float) -> str | None:
    if np.isnan(round_no):
        return None
    for low, high in TRANCHES:
        if low <= round_no <= high:
            return f"{low}+" if high >= 99 else f"{low}-{high}"
    return None


# ------------------------------------------------------------------------------ agrégats


def delta_interval(group: pd.DataFrame, resamples: int) -> dict | None:
    """Intervalle de l'écart moyen `B1 − modèle` du log-loss (blocs de journées, strates = saisons)."""
    sub = group[group["delta_b1"].notna()]
    if len(sub) < 2:
        return None
    blocks = bootstrap.block_keys(sub)
    if blocks.nunique() < MIN_BLOCKS:
        return {
            "mean": float(sub["delta_b1"].mean()),
            "low": None,
            "high": None,
            "n": int(len(sub)),
            "n_blocks": int(blocks.nunique()),
        }
    interval = bootstrap.block_bootstrap(
        sub["delta_b1"].to_numpy(),
        blocks.to_numpy(),
        strata=sub["season_year"].to_numpy(),
        n_resamples=resamples,
        seed=SEED,
    )
    return {key: float(value) for key, value in interval.to_dict().items()}


def summarize(group: pd.DataFrame, resamples: int = N_RESAMPLES) -> dict:
    """Mesures d'un groupe de matchs."""
    with_b1 = group[group["delta_b1"].notna()]
    return {
        "n": int(len(group)),
        "log_loss": float(group["log_loss"].mean()),
        "rps": float(group["rps"].mean()),
        "brier_over_2_5": float(group["brier_over"].mean()),
        "hit_over_2_5": float(group["hit_over"].mean()),
        "predicted_over_2_5": float(group["p_over"].mean()),
        "observed_over_2_5": float(group["over"].mean()),
        "predicted_total": float(group["expected_total"].mean()),
        "observed_total": float(group["total"].mean()),
        "hit_1x2": float(group["hit_1x2"].mean()),
        "brier_1x2": float(group["brier_1x2"].mean()),
        "b1": {
            "n": int(len(with_b1)),
            "log_loss_b1": float(with_b1["log_loss_b1"].mean()),
            "delta": delta_interval(group, resamples),
        }
        if len(with_b1)
        else None,
    }


def table(frame: pd.DataFrame, by: list[str], resamples: int) -> list[dict]:
    """Une ligne par valeur des colonnes `by` : la clé, puis les mesures."""
    rows = []
    for key, part in frame.groupby(by, sort=True, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({"group": dict(zip(by, (_plain(k) for k in key), strict=True)), **summarize(part, resamples)})
    return rows


def period_rows(frame: pd.DataFrame, resamples: int, group: dict | None = None) -> list[dict]:
    """Lignes validation, test scellé, puis toutes les saisons (dans cet ordre) ; une période vide est omise."""
    rows = []
    for period in ("validation", "scelle", "tout"):
        part = frame if period == "tout" else frame[frame["period"] == period]
        if len(part):
            rows.append({"group": {**(group or {}), "period": period}, **summarize(part, resamples)})
    return rows


def _plain(value):
    return value.item() if hasattr(value, "item") else value


def slope_interval(x, y, blocks, strata=None, n_resamples: int = N_RESAMPLES, seed: int = SEED) -> dict | None:
    """Pente de la droite des moindres carrés de `y` sur `x`, et son intervalle (blocs de journées, par strate).

    Le rééchantillonnage tire des blocs entiers ; chaque tirage recalcule la pente à partir des sommes des blocs.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    frame = pd.DataFrame(
        {"x": x, "y": y, "b": np.asarray(blocks), "s": np.zeros(len(x), int) if strata is None else np.asarray(strata)}
    )
    frame["xy"], frame["xx"] = x * y, x * x
    grouped = (
        frame.groupby(["s", "b"], sort=True)
        .agg(n=("x", "size"), sx=("x", "sum"), sy=("y", "sum"), sxy=("xy", "sum"), sxx=("xx", "sum"))
        .reset_index()
    )
    columns = ["n", "sx", "sy", "sxy", "sxx"]

    def slope(n, sx, sy, sxy, sxx):
        with np.errstate(invalid="ignore", divide="ignore"):
            denominator = sxx - sx**2 / n
            return np.where(denominator > 1e-12, (sxy - sx * sy / n) / denominator, np.nan)

    point = float(slope(*(grouped[c].sum() for c in columns)))
    if np.isnan(point) or len(grouped) < MIN_BLOCKS:
        return None
    rng = np.random.default_rng(seed)
    totals = {c: np.zeros(n_resamples) for c in columns}
    for stratum in np.unique(grouped["s"]):
        index = np.flatnonzero((grouped["s"] == stratum).to_numpy())
        draws = index[rng.integers(0, len(index), size=(n_resamples, len(index)))]
        for c in columns:
            totals[c] += grouped[c].to_numpy()[draws].sum(axis=1)
    resampled = slope(*(totals[c] for c in columns))
    alpha = (1 - LEVEL) / 2
    low, high = np.nanquantile(resampled, [alpha, 1 - alpha])
    return {"slope": point, "low": float(low), "high": float(high), "n": int(len(x)), "n_blocks": int(len(grouped))}


def trend_slope(group: pd.DataFrame, column: str, demean_by: tuple[str, ...], resamples: int) -> dict | None:
    """Pente de `column` selon l'avancement (de la 1re à la dernière journée), après retrait des moyennes de `demean_by`."""
    sub = group[group["progress"].notna() & group[column].notna()]
    if len(sub) < MIN_TREND:
        return None
    x, y = sub["progress"].astype(float), sub[column].astype(float)
    if demean_by:
        keys = [sub[c] for c in demean_by]
        x, y = x - x.groupby(keys).transform("mean"), y - y.groupby(keys).transform("mean")
    return slope_interval(
        x.to_numpy(),
        y.to_numpy(),
        bootstrap.block_keys(sub).to_numpy(),
        strata=sub["season_year"].to_numpy(),
        n_resamples=resamples,
    )


def slope_row(group: pd.DataFrame, label: dict, demean_by: tuple[str, ...], resamples: int) -> dict:
    return {
        "group": label,
        "n": int(group["progress"].notna().sum()),
        "log_loss": trend_slope(group, "log_loss", demean_by, resamples),
        "rps": trend_slope(group, "rps", demean_by, resamples),
        "delta_b1": trend_slope(group, "delta_b1", demean_by, resamples),
    }


def slopes(frame: pd.DataFrame, names: dict[int, str], resamples: int) -> list[dict]:
    """Pentes : tous matchs (effets fixes championnat × saison), par championnat (effet fixe saison), puis chaque saison × championnat."""
    rows = [slope_row(frame, {"kind": "tous"}, ("api_league_id", "season_year"), resamples)]
    for league, part in frame.groupby("api_league_id", sort=True):
        label = {"kind": "championnat", "api_league_id": int(league), "competition": names[int(league)]}
        rows.append(slope_row(part, label, ("season_year",), resamples))
    for (league, season), part in frame.groupby(["api_league_id", "season_year"], sort=True):
        label = {
            "kind": "saison",
            "api_league_id": int(league),
            "competition": names[int(league)],
            "season_year": int(season),
        }
        rows.append(slope_row(part, label, (), resamples))
    return rows


def slope_summary(rows: list[dict]) -> dict:
    """Combien de pentes saison × championnat vont dans quel sens, et combien ont un intervalle qui exclut 0."""
    fine = [r for r in rows if r["group"]["kind"] == "saison"]
    summary = {"n_groups": len(fine)}
    for key in ("log_loss", "delta_b1"):
        found = [r[key] for r in fine if r[key] is not None]
        summary[key] = {
            "estimated": len(found),
            "negative": sum(s["slope"] < 0 for s in found),
            "positive": sum(s["slope"] > 0 for s in found),
            "excluding_zero_negative": sum(s["high"] < 0 for s in found),
            "excluding_zero_positive": sum(s["low"] > 0 for s in found),
        }
    return summary


def build_report(
    frame: pd.DataFrame, today: dt.date, data_version: str, excluded: dict, resamples: int = N_RESAMPLES
) -> dict:
    """Relevé complet, agrégats seulement. `frame` : sortie de `measures` puis `add_progress`."""
    names = frame.groupby("api_league_id")["competition"].first().to_dict()
    names = {int(k): v for k, v in names.items()}
    # L'évolution dans la saison ne se lit que sur des saisons terminées : une saison en cours n'a que ses
    # premières journées, qui fausseraient les tranches et donneraient des pentes extrapolées.
    done = frame[frame["season_complete"]]
    partial = (
        frame[~frame["season_complete"]]
        .groupby(["api_league_id", "season_year"])
        .agg(played=("round_no", "max"), n_rounds=("n_rounds", "first"))
        .reset_index()
    )
    tranche_rows = {"tous": table(done[done["tranche"].notna()], ["tranche"], resamples), "championnat": {}}
    for league, part in done[done["tranche"].notna()].groupby("api_league_id", sort=True):
        tranche_rows["championnat"][names[int(league)]] = table(part, ["tranche"], resamples)
    slope_rows = slopes(done, names, resamples)
    return {
        "date": today.isoformat(),
        "horizon": "H1",
        "data_version": data_version,
        "n_resamples": resamples,
        "seed": SEED,
        "seasons": sorted(int(s) for s in frame["season_year"].unique()),
        "models": {
            season_label(int(s)): sorted(part["model_version"].unique()) for s, part in frame.groupby("season_year")
        },
        "excluded": dict(excluded),
        "competitions": {str(k): v for k, v in names.items()},
        "overall": period_rows(frame, resamples),
        "by_league": [
            row
            for league, part in frame.groupby("api_league_id", sort=True)
            for row in period_rows(part, resamples, {"api_league_id": int(league)})
        ],
        "by_season": table(frame, ["season_year"], resamples),
        "by_league_season": table(frame, ["api_league_id", "season_year"], resamples),
        "trend_seasons": sorted(int(s) for s in done["season_year"].unique()),
        "partial_seasons": [
            {
                "api_league_id": int(r.api_league_id),
                "season_year": int(r.season_year),
                "played": int(r.played),
                "n_rounds": int(r.n_rounds),
            }
            for r in partial.itertuples()
        ],
        "tranches": tranche_rows,
        "slopes": slope_rows,
        "slope_summary": slope_summary(slope_rows),
    }


# ------------------------------------------------------------------------------ rendu


def _delta(b1: dict | None) -> str:
    if not b1 or not b1["delta"]:
        return "—"
    d = b1["delta"]
    if d["low"] is None:
        return f"{d['mean']:+.4f} (moins de {MIN_BLOCKS} journées : pas d'intervalle)"
    return f"{d['mean']:+.4f} [{d['low']:+.4f} ; {d['high']:+.4f}]"


def _slope(found: dict | None) -> str:
    return "—" if found is None else f"{found['slope']:+.4f} [{found['low']:+.4f} ; {found['high']:+.4f}]"


def _grid(headers: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] + [
        "| " + " | ".join(r) + " |" for r in rows
    ]


def _measure_row(label: str, row: dict) -> list[str]:
    return [
        label,
        str(row["n"]),
        f"{row['log_loss']:.4f}",
        f"{row['rps']:.4f}",
        f"{row['brier_over_2_5']:.4f}",
        f"{row['hit_over_2_5']:.1%}",
        f"{row['predicted_total']:.2f} / {row['observed_total']:.2f}",
        f"{row['hit_1x2']:.1%}",
        _delta(row["b1"]),
    ]


MEASURE_HEADERS = [
    "Groupe",
    "Matchs",
    "Log-loss",
    "RPS",
    "Brier > 2,5",
    "Bons > 2,5",
    "Buts prévus / observés",
    "Bon vainqueur",
    "Écart à B1 [IC 95 %]",
]
EXCLUSION_LABELS = {
    "unavailable": "indisponible(s)",
    "out_of_scope": "hors périmètre",
    "excluded": "exclu(s) du jeu",
    "sans_score": "sans score",
    "sans_prediction": "sans prédiction",
}
PERIOD_LABELS = dict(PERIODS) | {"tout": "Toutes les saisons"}


def render(report: dict) -> str:
    names = {int(k): v for k, v in report["competitions"].items()}
    lines = [
        f"# Rejeu H1 de tous les matchs — relevé du {report['date']}",
        "",
        "Produit par `python -m foot_predictor.inference rejeu-stats`. **Relevé descriptif** : aucune règle de décision, "
        "aucun modèle changé à partir de lui. Agrégats seulement ; aucune cote.",
        "",
        f"- Données : `{report['data_version']}` ; horizon H1 ; saisons {', '.join(season_label(s) for s in report['seasons'])} ; "
        f"{sum(r['n'] for r in report['by_season'])} matchs prédits.",
        f"- Exclus (comptés, jamais devinés) : {', '.join(f'{v} {EXCLUSION_LABELS.get(k, k)}' for k, v in report['excluded'].items()) or 'aucun'}.",
        f"- Intervalles à 95 % par rééchantillonnage de blocs de journées ({report['n_resamples']} tirages, graine {report['seed']}).",
        "- **Écart à B1** : `B1 − modèle` du log-loss, positif = le modèle fait mieux que la moyenne de buts du championnat sur 3 saisons.",
        "- **Bons > 2,5** : part des matchs où le côté de 50 % de P(T > 2,5) était le bon. **Bon vainqueur** : le résultat 1/N/2 le plus "
        "probable (Poissons indépendants) était le bon ; hasard ≈ 45 %, descriptif, non validé par le protocole.",
        "- 2021-22 à 2024-25 : modèles et réglages choisis sur ces saisons. **Seules 2025-26 et 2026-27 sont vierges.**",
        "",
        "## Toutes saisons",
        "",
    ]
    lines += _grid(MEASURE_HEADERS, [_measure_row(PERIOD_LABELS[r["group"]["period"]], r) for r in report["overall"]])
    lines += ["", "## Par championnat", ""]
    rows = []
    for r in report["by_league"]:
        league, period = r["group"]["api_league_id"], r["group"]["period"]
        rows.append(_measure_row(f"{names[league]} — {PERIOD_LABELS[period]}", r))
    lines += _grid(MEASURE_HEADERS, rows)
    lines += ["", "## Par saison", ""]
    lines += _grid(
        MEASURE_HEADERS, [_measure_row(season_label(r["group"]["season_year"]), r) for r in report["by_season"]]
    )
    lines += ["", "## Par saison et par championnat", ""]
    lines += _grid(
        MEASURE_HEADERS,
        [
            _measure_row(f"{names[r['group']['api_league_id']]} {season_label(r['group']['season_year'])}", r)
            for r in report["by_league_season"]
        ],
    )
    lines += [
        "",
        "## Les prédictions sont-elles plus fiables en avançant dans la saison ?",
        "",
        f"**Saisons terminées seulement** ({', '.join(season_label(s) for s in report['trend_seasons'])}) : une saison en cours "
        "n'a que ses premières journées, qui fausseraient la comparaison"
        + (
            " ("
            + ", ".join(
                f"{names[p['api_league_id']]} {season_label(p['season_year'])} : {p['played']} journées sur {p['n_rounds']}"
                for p in report["partial_seasons"]
            )
            + ")"
            if report["partial_seasons"]
            else ""
        )
        + ".",
        "",
        "Par tranche de journées, tous championnats (journée du championnat, pas la date) :",
        "",
    ]
    lines += _grid(
        MEASURE_HEADERS, [_measure_row(f"journées {r['group']['tranche']}", r) for r in report["tranches"]["tous"]]
    )
    for competition, rows_by_league in report["tranches"]["championnat"].items():
        lines += ["", f"{competition} :", ""]
        lines += _grid(MEASURE_HEADERS, [_measure_row(f"journées {r['group']['tranche']}", r) for r in rows_by_league])
    lines += [
        "",
        "Pente de l'erreur selon l'avancement : variation entre la 1re et la dernière journée de la saison (droite des moindres "
        "carrés ; avancement = (journée − 1) / (nombre de journées − 1)). **Log-loss et RPS : négatif = meilleur en fin de saison. "
        "Écart à B1 : positif = l'avantage sur B1 grandit.** « Tous » retire les moyennes de chaque championnat × saison ; "
        "« championnat » retire celles de chaque saison.",
        "",
    ]
    slope_rows = []
    for r in report["slopes"]:
        g = r["group"]
        label = {
            "tous": "Tous (championnat × saison à effet fixe)",
            "championnat": f"{g.get('competition')} (saisons à effet fixe)",
            "saison": f"{g.get('competition')} {season_label(g['season_year']) if 'season_year' in g else ''}",
        }[g["kind"]]
        slope_rows.append([label, str(r["n"]), _slope(r["log_loss"]), _slope(r["rps"]), _slope(r["delta_b1"])])
    lines += _grid(
        [
            "Groupe",
            "Matchs",
            "Pente du log-loss [IC 95 %]",
            "Pente du RPS [IC 95 %]",
            "Pente de l'écart à B1 [IC 95 %]",
        ],
        slope_rows,
    )
    summary = report["slope_summary"]
    ll, db = summary["log_loss"], summary["delta_b1"]
    lines += [
        "",
        f"Sur les {summary['n_groups']} groupes saison × championnat : pente du log-loss négative dans {ll['negative']} sur "
        f"{ll['estimated']} (intervalle excluant 0 : {ll['excluding_zero_negative']} dans le sens « meilleur en fin de saison », "
        f"{ll['excluding_zero_positive']} dans l'autre) ; pente de l'écart à B1 positive dans {db['positive']} sur {db['estimated']} "
        f"(intervalle excluant 0 : {db['excluding_zero_positive']} positifs, {db['excluding_zero_negative']} négatifs). "
        f"Avec {summary['n_groups']} groupes, environ {0.05 * summary['n_groups']:.1f} intervalles excluent 0 par hasard seul.",
        "",
        "## Lecture",
        "",
        "- Descriptif : aucune conclusion de performance ne se tire d'un seul groupe. Un groupe saison × championnat compte environ "
        "300 à 380 matchs, une tranche en compte 60 à 70 : les intervalles sont larges.",
        "- Le log-loss absolu dépend aussi du nombre de buts de la période (plus de buts, loi plus étalée) : l'écart à B1 est la "
        "mesure à privilégier pour comparer des périodes.",
        "- La journée est celle du calendrier du championnat : un match reporté garde sa journée d'origine.",
        "- Les analyses sont nombreuses : un intervalle qui exclut 0 dans l'une d'elles ne prouve rien seul.",
    ]
    return "\n".join(lines) + "\n"
