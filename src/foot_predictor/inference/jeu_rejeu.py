"""Jeu de données du rejeu H1 (`python -m foot_predictor.inference jeu-rejeu`, ADR-0054).

Un fichier CSV, une ligne par match de championnat du top 5 rejoué depuis 2021-22, pour l'analyser dans un
notebook sans refaire le rejeu. Chaque ligne porte :

- l'identité du match (date, championnat, saison, journée, équipes) et les versions du modèle et des données ;
- les **variables que le modèle a lues** : `home_<variable>` est la valeur dans la ligne qui sert à prédire le λ
  du domicile, `away_<variable>` celle de la ligne du λ de l'extérieur (`opp_*` désigne l'adversaire de la
  ligne : `home_opp_elo_pre` égale donc `away_elo_pre`). `is_home` et `api_league_id` ne sont pas répétés ; une colonne
  que le modèle de la saison ne lit pas (demi-vie `_h120` ou `_h240`, choisie par pli) reste vide ;
- les **prédictions finales** : λ des deux équipes, loi du total `p0` à `p10` (`p10` = 10 buts ou plus),
  intervalle [q10 ; q90] et sa couverture annoncée, λ de la référence B1 ;
- le **score réel**, puis les mesures de chaque match (`rejeu_stats.measures` et `add_progress`) : pertes,
  bons « plus/moins de 2,5 », vainqueur déduit des λ, écart à B1, avancement dans la saison ;
- `traced_live` : le match a aussi été prédit en live, avant son coup d'envoi (journal `ops.prediction`).

**Alimentation.** Le fichier s'agrandit à chaque lancement : la commande compare les matchs joués du périmètre
à ceux du fichier et ne rejoue que les jours des matchs absents (premier lancement : tout, une quarantaine de
minutes ; ensuite quelques secondes à quelques minutes). Une ligne est identifiée par (jour, championnat,
équipe à domicile, équipe à l'extérieur), jamais par `match_id`, qui change d'un chargement à l'autre (E-058).
Les colonnes dérivées sont recalculées sur tout le fichier à chaque fois (l'avancement dans la saison dépend
des journées jouées). Si le modèle d'une saison a changé depuis les lignes déjà écrites, la commande s'arrête :
mélanger deux modèles serait silencieux, `--rebuild` refait tout.

Le fichier contient des scores de matchs scellés : il reste dans `data/inference/`, non suivi par Git.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path

import pandas as pd

from foot_predictor.inference import models, rejeu_stats
from foot_predictor.inference.prospective import prediction_frame

DATA_FILE = models.REPO_ROOT / "data" / "inference" / "jeu_rejeu_h1.csv"
DEFAULT_MAX_DAYS = 45
"""Jours rejoués au plus par lancement : un passage planifié ne refait pas, par erreur, tout le rejeu."""
KEY = ["match_day", "api_league_id", "home_team", "away_team"]
SIDES = {"domicile": "home", "exterieur": "away"}
NOT_REPEATED = ("is_home", "api_league_id")
"""Variables du modèle qui ne portent aucune information de plus : le côté et le championnat ont leur colonne."""
IDENTITY = [
    "match_day", "kickoff_utc", "season_year", "season", "api_league_id", "competition", "round",
    "home_team", "away_team", "model_version", "data_version",
]  # fmt: skip
PREDICTION = [
    "lambda_home", "lambda_away", *rejeu_stats.P_COLUMNS, "interval_low", "interval_high", "announced_coverage",
    "lambda_b1_home", "lambda_b1_away",
]  # fmt: skip
RESULT = ["home_goals", "away_goals"]
DERIVED = (
    "total", "log_loss", "rps", "p_over", "over", "brier_over", "hit_over", "expected_total", "p_home", "p_draw",
    "p_away", "hit_1x2", "brier_1x2", "log_loss_b1", "delta_b1", "period", "round_no", "n_rounds",
    "season_complete", "progress", "tranche", "traced_live",
)  # fmt: skip
"""Colonnes recalculées sur tout le fichier à chaque lancement ; les autres sont écrites une fois."""


class ModelChanged(RuntimeError):
    """Le modèle d'une saison n'est plus celui des lignes déjà écrites."""


class TooManyDays(RuntimeError):
    """Plus de jours à rejouer que le plafond du lancement."""


# ------------------------------------------------------------------------------ lignes d'un rejeu


def answers_frame(answers: list[dict]) -> tuple[pd.DataFrame, Counter]:
    """Réponses de `predict_day` → une ligne par match prédit avec score réel, variables lues et prédictions."""
    rows, skipped = [], Counter()
    for answer in answers:
        prediction, score = answer.get("prediction"), answer.get("actual_score")
        if prediction is None:
            skipped[answer.get("status") or "sans_prediction"] += 1
            continue
        if not score or score.get("home") is None or score.get("away") is None:
            skipped["sans_score"] += 1
            continue
        distribution, interval = prediction["total_distribution"], prediction["interval"]
        row = {
            "match_id": answer["match_id"],  # sert à B1 ; n'est pas écrit (instable, E-058)
            "match_day": dt.date.fromisoformat(answer["date"]),
            "kickoff_utc": answer.get("kickoff_utc"),
            "season_year": answer["season"],
            "season": rejeu_stats.season_label(answer["season"]),
            "api_league_id": answer["api_league_id"],
            "competition": answer["competition"],
            "round": answer["round"],
            "home_team": answer["home_team"],
            "away_team": answer["away_team"],
            "model_version": answer["model_version"],
            "data_version": answer["data_version"],
        }
        for item in answer["availability"]:
            if item["variable"] not in NOT_REPEATED:
                row[f"{SIDES[item['side']]}_{item['variable']}"] = item["value"]
        row.update(
            lambda_home=prediction["lambda_home"],
            lambda_away=prediction["lambda_away"],
            **{f"p{k}": float(distribution[label]) for k, label in enumerate(rejeu_stats.LABELS)},
            interval_low=interval["low"],
            interval_high=interval["high"],
            announced_coverage=interval["announced_coverage"],
            home_goals=int(score["home"]),
            away_goals=int(score["away"]),
        )
        rows.append(row)
    return pd.DataFrame(rows), skipped


def keyed_scope(context, since_season: int = rejeu_stats.FIRST_SEASON) -> pd.DataFrame:
    """Matchs joués du périmètre du rejeu, avec les noms d'équipes qui forment la clé d'une ligne."""
    scope = rejeu_stats.replay_scope(context.matches, since_season).copy()
    scope["home_team"] = scope["home_team_id"].map(context.team_names)
    scope["away_team"] = scope["away_team_id"].map(context.team_names)
    return scope


def keys(frame: pd.DataFrame) -> set[tuple]:
    return set(zip(*(frame[column] for column in KEY), strict=True))


def pending_days(scope: pd.DataFrame, done: set[tuple]) -> list[dt.date]:
    """Jours du périmètre qui ont au moins un match absent du fichier."""
    absent = [key not in done for key in zip(*(scope[column] for column in KEY), strict=True)]
    return sorted(scope.loc[absent, "match_day"].unique())


def replay_days(context, days: list[dt.date], scope: pd.DataFrame, predict=None, progress=None):
    """Rejoue `days` (modèle du pli, score réel, sans cote) ; renvoie les lignes avec B1 et les exclusions."""
    if predict is None:
        from foot_predictor.inference.predict import predict_day as predict
    competition_ids = sorted(int(c) for c in scope["competition_id"].unique())
    parts, excluded = [], Counter()
    for done, day in enumerate(days, start=1):
        part, skipped = answers_frame(predict(day, "replay", context, competition_ids, horizon="H1"))
        if not part.empty:
            parts.append(part)
        excluded.update(skipped)
        if progress is not None and (done % 25 == 0 or done == len(days)):
            progress(done, len(days))
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not frame.empty:
        frame = rejeu_stats.add_b1(frame, context.matches)
    return frame, excluded


# ------------------------------------------------------------------------------ fichier


def read(path: Path) -> pd.DataFrame:
    """Colonnes écrites une fois, telles qu'elles étaient ; `float_precision` évite d'arrondir à la relecture."""
    frame = pd.read_csv(path, float_precision="round_trip")
    frame["match_day"] = pd.to_datetime(frame["match_day"]).dt.date
    return frame[[c for c in frame.columns if c not in DERIVED]]


def check_models(existing: pd.DataFrame, new: pd.DataFrame) -> None:
    """Refuse de mélanger deux modèles dans une même saison."""
    if existing.empty or new.empty:
        return
    before = existing.groupby("season_year")["model_version"].agg(set)
    after = new.groupby("season_year")["model_version"].agg(set)
    changed = sorted(s for s in before.index.intersection(after.index) if before[s] != after[s])
    if changed:
        raise ModelChanged(
            "Le modèle a changé pour la saison "
            + ", ".join(rejeu_stats.season_label(int(s)) for s in changed)
            + " depuis les lignes du fichier : `--rebuild` refait tout le rejeu."
        )


def merge(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les lignes de `new` ; une ligne de même clé est remplacée. Triées par jour, coup d'envoi, championnat."""
    new = new.drop(columns=["match_id"], errors="ignore")
    if existing.empty:
        both = new
    elif new.empty:
        both = existing
    else:
        fresh = keys(new)
        replaced = existing[[key not in fresh for key in zip(*(existing[c] for c in KEY), strict=True)]]
        both = pd.concat([replaced, new], ignore_index=True)
    return both.sort_values(["match_day", "kickoff_utc", "api_league_id", "home_team"], kind="stable").reset_index(
        drop=True
    )


def traced_keys(scope: pd.DataFrame, journal_rows: list[dict]) -> set[tuple]:
    """Clés des matchs du périmètre prédits en live **avant** leur coup d'envoi (journal prospectif).

    Appariement par identifiant API quand la prédiction en a un, sinon par identifiant interne (E-058)."""
    journal = prediction_frame(journal_rows)
    if journal.empty:
        return set()
    before = journal[journal["created_at"] < journal["kickoff_utc"]]
    with_fixture = before["api_fixture_id"].notna()
    fixtures = {int(v) for v in before.loc[with_fixture, "api_fixture_id"]}
    internal = {int(v) for v in before.loc[~with_fixture, "match_id"]}
    hit = scope["api_fixture_id"].map(lambda v: pd.notna(v) and int(v) in fixtures) | scope["match_id"].isin(internal)
    return keys(scope[hit])


def with_derived(frame: pd.DataFrame, traced: set[tuple]) -> pd.DataFrame:
    """Colonnes dérivées recalculées sur tout le fichier, puis ordre des colonnes."""
    out = rejeu_stats.add_progress(rejeu_stats.measures(frame))
    out["tranche"] = out["tranche"].astype(object)
    out["traced_live"] = [key in traced for key in zip(*(out[c] for c in KEY), strict=True)]
    variables = [
        c
        for c in out.columns
        if c.startswith(("home_", "away_")) and c not in ("home_team", "away_team") + tuple(RESULT)
    ]
    first = IDENTITY + sorted(variables, key=lambda c: (c.split("_", 1)[1], c)) + PREDICTION + RESULT
    rest = [c for c in out.columns if c not in first]
    return out[first + rest]


def write(frame: pd.DataFrame, path: Path, meta: dict) -> None:
    """Écrit le CSV et son `.meta.json` sans jamais laisser un fichier à moitié écrit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update(
    context,
    journal_rows: list[dict],
    path: Path = DATA_FILE,
    *,
    rebuild: bool = False,
    max_days: int = DEFAULT_MAX_DAYS,
    since_season: int = rejeu_stats.FIRST_SEASON,
    predict=None,
    progress=None,
) -> dict:
    """Met le fichier à jour : rejoue les jours des matchs absents, fusionne, recalcule, écrit. Renvoie un bilan."""
    scope = keyed_scope(context, since_season)
    existing = pd.DataFrame() if rebuild or not path.exists() else read(path)
    days = pending_days(scope, set() if existing.empty else keys(existing))
    if max_days and len(days) > max_days:
        raise TooManyDays(
            f"{len(days)} jours à rejouer, plus que --max-days {max_days} : "
            "relancer avec --max-days 0 (premier lancement : environ 40 minutes)."
        )
    new, excluded = replay_days(context, days, scope, predict, progress) if days else (pd.DataFrame(), Counter())
    check_models(existing, new)
    before = 0 if existing.empty else len(existing)
    merged = merge(existing, new)
    if merged.empty:
        return {"days": 0, "added": 0, "total": 0, "excluded": dict(excluded), "written": False}
    frame = with_derived(merged, traced_keys(scope, journal_rows))
    meta = {
        "updated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "data_version": context.data_version,
        "rows": int(len(frame)),
        "first_day": min(frame["match_day"]).isoformat(),
        "last_day": max(frame["match_day"]).isoformat(),
        "models": {
            rejeu_stats.season_label(int(s)): sorted(v)
            for s, v in frame.groupby("season_year")["model_version"].agg(set).items()
        },
        "excluded_last_replay": dict(excluded),
    }
    write(frame, path, meta)
    return {
        "days": len(days),
        "added": len(frame) - before,
        "total": len(frame),
        "excluded": dict(excluded),
        "written": True,
        "path": str(path),
    }
