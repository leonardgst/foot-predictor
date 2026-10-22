"""Contrôles sur données réelles (`python -m foot_predictor.inference check`), rapport dans `reports/inference/`.

Les données locales (table des matchs de `staging`, jeu versionné) manquent en CI : ces contrôles
sont donc une commande, et non des tests automatisés (ADR-0040). Ils ne lisent que la période de
développement (porte `features/sources.py`), sauf `rows-scelle` (ci-dessous).

Contrôle des lignes (décision 2, test (a)) : pour un échantillon de jours des quatre saisons de
validation et des cas limites (première journée d'une saison et ses promus, Ligue 1 à 18 clubs,
huis clos), les lignes d'inférence du jour doivent être **identiques au bit près** aux lignes du
jeu d'entraînement pour les mêmes matchs, toutes colonnes sauf celles d'après-match. Les lignes se
rapprochent par (`match_id`, `team_id`), identifiants internes qui changent quand le brut grandit
(E-058) : le jeu comparé doit venir du **même chargement** de `staging` que la table lue, ce que le
rapport vérifie.

Contrôle des lignes sur la période scellée (`rows-scelle`, 5.13, ADR-0045), seulement sur demande :
la même comparaison, sur des jours de 2025-26 et du début de 2026-27, entre l'inférence (table
ouverte à l'inférence) et le jeu scellé `ds-2026-10-22-94969da0`, celui du test scellé et du
modèle final. La lecture du jeu scellé est journalisée ; le rapport ne donne que des décomptes et
des noms de colonnes, aucune valeur.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.inference.rows import POST_MATCH_COLUMNS, rows_for_day
from foot_predictor.seal import SEAL_DATE

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports" / "inference"
DATASET_VERSION = "ds-2026-09-30-ba2b91f7"
"""Jeu de l'évaluation (expérience d'ablation) : celui que reproduisent les contrôles `replay` et `predictions`."""
ROWS_DATASET_VERSION = "ds-2026-10-22-bf786ef1"
"""Jeu du contrôle `rows` : construit sur le chargement n° 7 de `staging`, celui en vigueur (3.11, E-058)."""
SEALED_DATASET_VERSION = "ds-2026-10-22-94969da0"
"""Jeu construit avec `--sealed-test` (4.16) : celui du test scellé H1 et du modèle final (ADR-0044)."""


def sample_days(dataset: pd.DataFrame) -> list[tuple[dt.date, str]]:
    """Jours contrôlés, avec la raison de leur choix (déterministe : aucun tirage)."""
    top5 = dataset[dataset["eval_population"]]
    days: list[tuple[dt.date, str]] = []
    for season in (2021, 2022, 2023, 2024):
        season_days = sorted(top5.loc[top5["season_year"] == season, "match_day"].unique())
        days += [
            (season_days[0], f"première journée {season}-{(season + 1) % 100:02d} (promus sans historique de D1)"),
            (season_days[len(season_days) // 2], f"milieu de saison {season}-{(season + 1) % 100:02d}"),
            (season_days[-1], f"dernier jour {season}-{(season + 1) % 100:02d}"),
        ]
        season_rows = top5[top5["season_year"] == season].groupby("match_day").size()
        days.append((season_rows.idxmax(), f"jour le plus chargé {season}-{(season + 1) % 100:02d}"))
    ligue1 = sorted(top5.loc[(top5["api_league_id"] == 61) & (top5["season_year"] == 2023), "match_day"].unique())
    days.append((ligue1[0], "Ligue 1 à 18 clubs, première journée 2023-24"))
    closed = sorted(
        dataset.loc[(dataset["behind_closed_doors"] == 1) & dataset["eval_population"], "match_day"].unique()
    )
    days.append((closed[len(closed) // 2], "huis clos (2020-21)"))
    reasons: dict[dt.date, list[str]] = {}
    for day, reason in days:
        reasons.setdefault(day, []).append(reason)  # un même jour peut servir deux cas limites
    return [(day, " ; ".join(r)) for day, r in reasons.items()]


def sealed_sample_days(dataset: pd.DataFrame) -> list[tuple[dt.date, str]]:
    """Jours contrôlés sur la période scellée, avec la raison de leur choix (déterministe : aucun tirage)."""
    top5 = dataset[dataset["eval_population"] & (dataset["season_year"] >= SEAL_DATE.year)]  # saison = 1er juillet
    days: list[tuple[dt.date, str]] = []
    for season in sorted(int(s) for s in top5["season_year"].unique()):
        label = f"{season}-{(season + 1) % 100:02d}"
        season_rows = top5[top5["season_year"] == season]
        season_days = sorted(season_rows["match_day"].unique())
        days += [
            (season_days[0], f"première journée {label} (promus sans historique de D1)"),
            (season_days[len(season_days) // 2], f"milieu de la période {label}"),
            (season_days[-1], f"dernier jour présent {label}"),
            (season_rows.groupby("match_day").size().idxmax(), f"jour le plus chargé {label}"),
        ]
    reasons: dict[dt.date, list[str]] = {}
    for day, reason in days:
        reasons.setdefault(day, []).append(reason)
    return [(day, " ; ".join(r)) for day, r in reasons.items()]


def compare_day(matches: pd.DataFrame, dataset: pd.DataFrame, day: dt.date, **params) -> dict:
    """Lignes d'inférence du jour contre lignes du jeu pour les mêmes matchs ; colonnes en écart."""
    started = time.perf_counter()
    rows = rows_for_day(matches, day, **params)
    seconds = time.perf_counter() - started
    expected = dataset[dataset["match_day"] == day].drop(columns=list(POST_MATCH_COLUMNS))
    keys = ["match_id", "team_id"]
    rows = rows.sort_values(keys).reset_index(drop=True)
    expected = expected.sort_values(keys).reset_index(drop=True)[rows.columns] if len(rows) else expected
    differing = []
    same_keys = len(rows) == len(expected) and rows[keys].equals(expected[keys])
    if same_keys:
        for column in rows.columns:
            try:
                pd.testing.assert_series_equal(rows[column], expected[column], check_names=False)
            except AssertionError:
                differing.append(column)
    return {
        "day": day.isoformat(),
        "rows": int(len(rows)),
        "expected_rows": int(len(expected)),
        "same_matches": bool(same_keys),
        "differing_columns": differing,
        "identical": bool(same_keys and not differing),
        "seconds": round(seconds, 2),
    }


def run_rows_check(
    matches: pd.DataFrame | None = None,
    dataset: pd.DataFrame | None = None,
    manifest: dict | None = None,
    staging_load_run: int | None = None,
) -> dict:
    """Lignes de l'inférence contre le jeu du chargement en vigueur ; `same_load_run` dit si le rapprochement
    par identifiants internes a un sens (None : chargement inconnu, données fournies par l'appelant)."""
    from foot_predictor.features.sources import load_dataset, load_matches

    if matches is None:
        from foot_predictor.db.session import get_engine
        from foot_predictor.inference.context import last_load_run

        engine = get_engine()
        matches = load_matches(engine)
        staging_load_run = last_load_run(engine)[0]
    if dataset is None:
        dataset, manifest = load_dataset(ROWS_DATASET_VERSION)
    dataset_load_run = (manifest or {}).get("load_run_id")
    same = None if dataset_load_run is None or staging_load_run is None else dataset_load_run == staging_load_run
    results = []
    for day, reason in sample_days(dataset):
        result = compare_day(matches, dataset, day)
        result["reason"] = reason
        results.append(result)
    return {
        "dataset": (manifest or {}).get("version", ROWS_DATASET_VERSION),
        "load_runs": {"dataset": dataset_load_run, "staging": staging_load_run},
        "same_load_run": same,
        "days": results,
        "all_identical": all(r["identical"] for r in results),
        "rows_compared": sum(r["rows"] for r in results),
    }


def run_sealed_rows_check(matches: pd.DataFrame | None = None, dataset: pd.DataFrame | None = None) -> dict:
    """Lignes de l'inférence (historique ouvert) contre le jeu scellé, sur des jours de la période scellée."""
    from foot_predictor.features.sources import load_dataset, load_matches
    from foot_predictor.seal import H1_SEALED_EXPERIMENT

    if matches is None:
        matches = load_matches(opened_for_inference=True)
    if dataset is None:
        dataset, _ = load_dataset(SEALED_DATASET_VERSION, sealed_test=True, experiment=H1_SEALED_EXPERIMENT)
    results = []
    for day, reason in sealed_sample_days(dataset):
        result = compare_day(matches, dataset, day, history_opened=True)
        result["reason"] = reason
        results.append(result)
    return {
        "dataset": SEALED_DATASET_VERSION,
        "days": results,
        "all_identical": all(r["identical"] for r in results),
        "rows_compared": sum(r["rows"] for r in results),
    }


def render_sealed_rows(report: dict) -> str:
    _, body = render_rows(report).split("\n", 1)  # même tableau que `render_rows`, autre titre
    return (
        f"# Contrôle des lignes d'inférence sur la période scellée, contre le jeu {report['dataset']} — "
        f"{report['date']}\n\n"
        "Sous-étape 5.13 (ADR-0045) : table des matchs ouverte à l'inférence, jeu scellé du test H1 et du modèle "
        "final (lecture journalisée dans `reports/sealed_tests.md`). Ce rapport ne donne que des dates, des décomptes "
        "et des noms de colonnes : aucune valeur d'un match scellé.\n" + body
    )


def render_rows(report: dict) -> str:
    lines = [
        f"# Contrôle des lignes d'inférence contre le jeu {report['dataset']} — {report['date']}",
        "",
        "Produit par `python -m foot_predictor.inference check` (ADR-0040, décision 2). Lignes d'inférence d'un jour "
        "(historique tronqué au jour J, cibles à 0-0 sans statistiques) contre lignes du jeu d'entraînement pour les "
        "mêmes matchs ; toutes colonnes sauf `goals_for`, `goals_against`, `shots_source`.",
        "",
        f"**Verdict : {'identiques au bit près' if report['all_identical'] else 'ÉCART'}** sur {len(report['days'])} "
        f"jours et {report['rows_compared']} lignes.",
        "",
    ]
    if "load_runs" in report:  # contrôle `rows` : même chargement de `staging` que le jeu (E-058)
        runs, same = report["load_runs"], report["same_load_run"]
        verdict = {
            True: "même chargement",
            False: "**CHARGEMENTS DIFFÉRENTS** : rapprochement sans objet",
            None: "inconnu",
        }
        lines += [f"Chargement du jeu : n° {runs['dataset']} ; chargement de `staging` lu : n° {runs['staging']} "
                  f"({verdict[same]}).", ""]  # fmt: skip
    lines += [
        "| Jour | Raison du choix | Lignes | Identiques | Colonnes en écart | Durée (s) |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["days"]:
        lines.append(
            f"| {r['day']} | {r['reason']} | {r['rows']} | {'oui' if r['identical'] else 'NON'} | "
            f"{', '.join(r['differing_columns']) or 'aucune'} | {r['seconds']:.1f} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: dict, name: str, markdown: str, reports_dir: Path = REPORTS_DIR) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{name}.json"
    md_path = reports_dir / f"{name}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(markdown, encoding="utf-8", newline="\n")
    return json_path, md_path


# ------------------------------------------------------------------------------ reproduction du rejeu

ABLATION_REPORT = "ablations-20260930T110352"
ABLATION_MODEL = "A2_G0G2"


def run_replay_check(dataset: pd.DataFrame | None = None, manifest: dict | None = None) -> dict:
    """Décision 3 : les modèles de rejeu reproduisent les prédictions de l'évaluation (ablation A2_G0G2).

    Pour chaque saison de validation S : modèle de rejeu du pli S (entraîné ou lu dans le cache),
    prédictions des matchs du top 5 de S, comparées match par match à celles de l'expérience.
    """
    import numpy as np

    from foot_predictor.features.sources import load_dataset
    from foot_predictor.inference.models import replay_model
    from foot_predictor.modeling import protocol

    if dataset is None:
        dataset, manifest = load_dataset(DATASET_VERSION)
    reference = pd.read_parquet(REPO_ROOT / "data" / "experiments" / ABLATION_REPORT / "predictions.parquet")
    reference = reference[reference["model"] == ABLATION_MODEL]
    seasons = []
    for season in (2021, 2022, 2023, 2024):
        started = time.perf_counter()
        loaded = replay_model(season, dataset, manifest)
        seconds = time.perf_counter() - started
        rows = protocol.test_rows(dataset, season)
        rows, _ = protocol.usable(rows, loaded.features)
        predicted = loaded.model.predict(protocol.complete_matches(rows))
        ref = reference[reference["fold"] == season].set_index("match_id").loc[predicted.match_id]
        p_cols = [c for c in ref.columns if c.startswith("p_total_")]
        seasons.append(
            {
                "season": season,
                "model": loaded.version,
                "half_life": loaded.card["model"]["params"].get("half_life"),
                "last_training_season": loaded.card["training"]["last_season"],
                "matches": int(len(predicted)),
                "reference_matches": int((reference["fold"] == season).sum()),
                "max_abs_lambda": float(
                    max(
                        np.abs(predicted.lambda_home - ref["lambda_home"].to_numpy()).max(),
                        np.abs(predicted.lambda_away - ref["lambda_away"].to_numpy()).max(),
                    )
                ),
                "max_abs_probability": float(np.abs(predicted.total - ref[p_cols].to_numpy()).max()),
                "seconds": round(seconds, 2),
            }
        )
    tolerance = 1e-9
    return {
        "reference": f"{ABLATION_REPORT} ({ABLATION_MODEL})",
        "tolerance": tolerance,
        "seasons": seasons,
        "all_reproduced": all(
            s["matches"] == s["reference_matches"]
            and s["max_abs_probability"] <= tolerance
            and s["max_abs_lambda"] <= tolerance
            for s in seasons
        ),
    }


def render_replay(report: dict) -> str:
    lines = [
        f"# Reproduction du rejeu — {report['date']}",
        "",
        "Produit par `python -m foot_predictor.inference check` (ADR-0040, décision 3). Modèle de rejeu de chaque saison "
        f"(pli S, appris sur 2015-16 à S − 1) contre les prédictions de l'expérience {report['reference']}, match par "
        f"match ; tolérance {report['tolerance']:g}.",
        "",
        f"**Verdict : {'reproduites' if report['all_reproduced'] else 'ÉCART'}.**",
        "",
        "| Saison | Modèle | Demi-vie | Dernière saison apprise | Matchs | Écart max. λ | Écart max. P(T = k) | Durée (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in report["seasons"]:
        lines.append(
            f"| {s['season']}-{(s['season'] + 1) % 100:02d} | `{s['model']}` | {s['half_life']} | "
            f"{s['last_training_season']}-{(s['last_training_season'] + 1) % 100:02d} | {s['matches']} / "
            f"{s['reference_matches']} | {s['max_abs_lambda']:.1e} | {s['max_abs_probability']:.1e} | {s['seconds']:.1f} |"
        )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ prédictions de journées


def run_predictions_check(context=None) -> dict:
    """Décision 3 (suite) : `predict_day` en rejeu reproduit l'évaluation sur des journées réelles.

    Pour les jours les plus chargés et les premières journées des quatre saisons de validation :
    prédictions de rejeu (lignes d'inférence, disponibilité, modèle du pli) contre prédictions de
    l'expérience d'ablation pour les mêmes matchs ; log-loss de la journée recalculé des deux côtés.
    """
    import numpy as np

    from foot_predictor.features.sources import load_dataset
    from foot_predictor.inference.context import build_context
    from foot_predictor.inference.predict import K_LABELS, predict_day
    from foot_predictor.modeling import metrics

    if context is None:
        context = build_context()
    dataset = context.dataset if context.dataset is not None else load_dataset(DATASET_VERSION)[0]
    reference = pd.read_parquet(REPO_ROOT / "data" / "experiments" / ABLATION_REPORT / "predictions.parquet")
    reference = reference[reference["model"] == ABLATION_MODEL].set_index("match_id")
    top5 = dataset[dataset["eval_population"]]
    days = []
    for season in (2021, 2022, 2023, 2024):
        per_day = top5[top5["season_year"] == season].groupby("match_day").size()
        days += [per_day.idxmax(), per_day.index.min()]
    results = []
    for day in days:
        started = time.perf_counter()
        answers = predict_day(day, "replay", context)
        seconds = time.perf_counter() - started
        predicted = [a for a in answers if a["prediction"] is not None]
        statuses = pd.Series([a["status"] for a in answers]).value_counts().to_dict()
        ids = [a["match_id"] for a in predicted]
        ours = np.array([[a["prediction"]["total_distribution"][k] for k in K_LABELS] for a in predicted])
        totals = np.array([a["actual_score"]["home"] + a["actual_score"]["away"] for a in predicted])
        ref = reference.loc[[i for i in ids if i in reference.index]]
        in_reference = len(ref) == len(ids)
        max_lambda = (
            float(max(np.abs(np.array([a["prediction"]["lambda_home"] for a in predicted]) - ref["lambda_home"].to_numpy()).max(),
                      np.abs(np.array([a["prediction"]["lambda_away"] for a in predicted]) - ref["lambda_away"].to_numpy()).max()))
            if in_reference and ids else None
        )  # fmt: skip
        ll_ours = float(metrics.log_loss_by_match(ours, totals).mean()) if ids else None
        ll_ref = (
            float(metrics.log_loss_by_match(ref[[f"p_total_{k}" for k in range(11)]].to_numpy(), totals).mean())
            if in_reference and ids else None
        )  # fmt: skip
        reasons = sorted({r for a in answers if a["prediction"] is None for r in a["reasons"]})
        results.append(
            {
                "day": pd.Timestamp(day).date().isoformat(),
                "matches": len(answers),
                "statuses": {str(k): int(v) for k, v in statuses.items()},
                "predicted": len(predicted),
                "in_reference": bool(in_reference),
                "max_abs_lambda": max_lambda,
                "log_loss_replay": ll_ours,
                "log_loss_evaluation": ll_ref,
                "reasons": reasons[:6],
                "seconds": round(seconds, 2),
            }
        )
    return {
        "reference": f"{ABLATION_REPORT} ({ABLATION_MODEL})",
        "days": results,
        "all_reproduced": all(
            r["in_reference"]
            and (r["max_abs_lambda"] or 0.0) <= 1e-9
            and (r["log_loss_replay"] is None or abs(r["log_loss_replay"] - r["log_loss_evaluation"]) <= 1e-9)
            for r in results
        ),
    }


def render_predictions(report: dict) -> str:
    lines = [
        f"# Prédictions de rejeu sur des journées réelles — {report['date']}",
        "",
        "Produit par `python -m foot_predictor.inference check` (ADR-0040). `predict_day` en rejeu (lignes d'inférence, "
        f"matrice de disponibilité, modèle du pli) contre l'expérience {report['reference']} pour les mêmes matchs.",
        "",
        f"**Verdict : {'reproduites' if report['all_reproduced'] else 'ÉCART'}.**",
        "",
        "| Jour | Matchs (toutes compétitions) | Statuts | Prédits | Écart max. λ | Log-loss rejeu | Log-loss évaluation | Durée (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in report["days"]:
        statuses = ", ".join(f"{k} {v}" for k, v in sorted(r["statuses"].items()))
        lam = "—" if r["max_abs_lambda"] is None else f"{r['max_abs_lambda']:.1e}"
        ll1 = "—" if r["log_loss_replay"] is None else f"{r['log_loss_replay']:.4f}"
        ll2 = "—" if r["log_loss_evaluation"] is None else f"{r['log_loss_evaluation']:.4f}"
        lines.append(f"| {r['day']} | {r['matches']} | {statuses} | {r['predicted']} | {lam} | {ll1} | {ll2} | "
                     f"{r['seconds']:.1f} |")  # fmt: skip
    reasons = sorted({reason for r in report["days"] for reason in r["reasons"]})
    if reasons:
        lines += ["", "Raisons rencontrées (matchs non prédits) :", ""] + [f"- {reason}" for reason in reasons]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ répétition du live

LIVE_FREEZE = dt.date(2024, 2, 15)
LIVE_TODAY = dt.date(2024, 3, 9)
FOLLOWING_DAYS = 7
"""Jours suivants de la répétition (ADR-0046) : matchs prédits avec la fraîcheur par équipe, avant leurs résultats."""
LAMBDA_TOLERANCE = 0.005
OVER_TOLERANCE = 0.002
"""Tolérance de l'ADR-0046, fixée avant la vérification : écart absolu de λ et de P(T > 2,5) dû à la règle par équipe."""
STAT_COLUMNS = (
    "home_shots_api", "home_sot_api", "home_xg_api", "away_shots_api", "away_sot_api", "away_xg_api",
    "home_shots_fd", "home_sot_fd", "away_shots_fd", "away_sot_fd",
)  # fmt: skip


def freeze_table(matches: pd.DataFrame, freeze: dt.date, season: int) -> pd.DataFrame:
    """Table des matchs telle que `staging` la verrait après un gel au jour `freeze` (copie).

    Matchs des 10 championnats de la saison, à partir de `freeze` : non joués, sans buts ni
    statistiques (le calendrier API figé). La suite vient de football-data, comme en live.
    """
    from foot_predictor.features.leagues import LADDERS

    table = matches.copy()
    after = (
        (table["season_year"] == season) & table["api_league_id"].isin(list(LADDERS)) & (table["match_day"] >= freeze)
    )
    table.loc[after, "status"] = "scheduled"
    for column in ("home_goals_90", "away_goals_90", *STAT_COLUMNS):
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce").astype("Float64")
            table.loc[after, column] = pd.NA
    return table


def _compare_columns(got: pd.DataFrame, expected: pd.DataFrame) -> dict[str, int] | None:
    """Nombre de lignes en écart par colonne (valeurs manquantes égales entre elles) ; None si les matchs diffèrent."""
    keys = ["match_id", "team_id"]
    got, expected = got.sort_values(keys).reset_index(drop=True), expected.sort_values(keys).reset_index(drop=True)
    if len(got) != len(expected) or not got[keys].equals(expected[keys]):
        return None
    counts = {}
    for column in got.columns:
        a, b = got[column], expected[column]
        same = (a == b).fillna(False).astype(bool) | (a.isna() & b.isna())
        counts[column] = int((~same).sum())
    return counts


def run_live_rehearsal(
    matches: pd.DataFrame | None = None,
    raw_dir: Path = REPO_ROOT / "data" / "raw",
    maps=None,
    freeze: dt.date = LIVE_FREEZE,
    today: dt.date = LIVE_TODAY,
    model=None,
) -> dict:
    """Répétition du live sur la période de développement (sous-étape 5.10, ADR-0042).

    Gel simulé au jour `freeze`, « aujourd'hui » simulé `today` : les CSV historiques de football-data
    de la saison, coupés aux matchs d'avant `today` (comme un fichier téléchargé ce matin-là), sont
    superposés à la table gelée. Les lignes des matchs de `today` sont comparées à celles de la vraie
    table : buts et Elo doivent être identiques (même fonction, mêmes résultats) ; seules les variables
    de tirs peuvent différer (tirs de football-data au lieu de ceux de l'API, ADR-0041).

    Jours suivants (`FOLLOWING_DAYS`, ADR-0046) : pour les matchs du top 5 que la fraîcheur par équipe
    déclare disponibles sans les résultats d'après `today`, comparaison avec la même superposition
    complétée de ces résultats (mêmes fichiers, donc mêmes tirs) : l'Elo doit être identique ; l'écart
    des variables G2 (a priori μ du championnat) est mesuré, et avec `model`, celui de λ et de
    P(T > 2,5), comparé à la tolérance de l'ADR-0046. On compte aussi les matchs que la fraîcheur par
    championnat aurait déclarés disponibles.
    """
    from foot_predictor.features.leagues import TOP5
    from foot_predictor.features.sources import load_matches
    from foot_predictor.inference import live_sources as L
    from foot_predictor.inference.availability import match_availability
    from foot_predictor.modeling.models.team import M3

    if matches is None:
        matches = load_matches()
    if maps is None:
        maps = L.TeamMaps.from_yaml(_api_to_internal())
    season = L.season_of(today)
    files = L.season_files(raw_dir, season)

    def cut_results(sources: dict, cut: dt.date) -> dict:
        """Les CSV de la saison coupés aux matchs d'avant `cut`, comme un fichier téléchargé ce matin-là."""
        fetched = dt.datetime.combine(cut, dt.time(8), tzinfo=dt.UTC)
        return {
            division: L.SourceFile(
                [r for r in source.rows if (L.parse_date(r.get("Date") or "") or cut) < cut], fetched, source.name
            )
            for division, source in sources.items()
        }

    results = cut_results(files, today)
    frozen = freeze_table(matches, freeze, season)
    started = time.perf_counter()
    live = L.overlay(frozen, maps, season, [], results, today)
    overlay_seconds = time.perf_counter() - started

    truth = matches[["match_id", "home_goals_90", "away_goals_90"]]
    window = live.matches.merge(truth, on="match_id", suffixes=("", "_api"))
    window = window[
        (window["season_year"] == season)
        & window["api_league_id"].isin(list(maps.division_to_league.values()))
        & (window["match_day"] >= freeze)
        & (window["match_day"] < today)
    ]
    played = window[window["status"] == "played"]
    mismatches = (played["home_goals_90"] != played["home_goals_90_api"]) | (
        played["away_goals_90"] != played["away_goals_90_api"]
    )

    got = rows_for_day(live.matches, today)
    columns = _compare_columns(got, rows_for_day(matches, today))
    differing = {c: n for c, n in (columns or {}).items() if n}
    features = tuple(M3(("G0", "G1", "G2"), 240).features)
    statuses: dict[str, int] = {}
    for _, match in live.matches[live.matches["match_day"] == today].iterrows():
        rows = got[got["match_id"] == match["match_id"]]
        status = match_availability(match, rows, features, live.freshness.get(int(match["api_league_id"]))).status
        statuses[status] = statuses.get(status, 0) + 1
    history = ("goals_", "opp_goals_", "elo", "opp_elo")
    following = []
    for offset in range(1, FOLLOWING_DAYS + 1):
        day = today + dt.timedelta(days=offset)
        on_day = live.matches[(live.matches["match_day"] == day) & live.matches["api_league_id"].isin(list(TOP5))]
        on_day = on_day[on_day["is_regular_season"].fillna(True).astype(bool)]
        if not on_day.empty:
            # Mêmes fichiers, résultats jusqu'à la veille du jour : seul l'effet de la règle par équipe reste.
            complete = L.overlay(frozen, maps, season, [], cut_results(files, day), day)
            following.append(_following_day(day, on_day, live, complete, features, model))
    return {
        "freeze": freeze.isoformat(),
        "today": today.isoformat(),
        "season": season,
        "matches_after_freeze": int(len(window)),
        "results_restored": int(len(played)),
        "score_mismatches": int(mismatches.sum()),
        "issues": [
            {"division": i.division, "date": i.date.isoformat() if i.date else None, "reason": i.reason}
            for i in live.issues
        ],
        "freshness": {str(k): v.complete_until.isoformat() for k, v in live.freshness.items()},
        "rows": int(len(got)),
        "same_matches": columns is not None,
        "differing_columns": differing,
        "goals_and_elo_identical": columns is not None and not any(c.startswith(history) for c in differing),
        "statuses": statuses,
        "overlay_seconds": round(overlay_seconds, 2),
        "following": following,
        "following_ok": all(_following_ok(d) for d in following),
        "tolerances": {"lambda": LAMBDA_TOLERANCE, "p_over_2_5": OVER_TOLERANCE},
    }


def _following_ok(day: dict) -> bool:
    """Jour suivant conforme à l'ADR-0046 : Elo identique, λ et P(T > 2,5) dans la tolérance (s'ils sont mesurés)."""
    lam, over = day["max_lambda_gap"], day["max_over_gap"]
    return (
        day["elo_identical"] == day["team_rule"]
        and (lam is None or lam <= LAMBDA_TOLERANCE)
        and (over is None or over <= OVER_TOLERANCE)
    )


def _gap(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Écart absolu maximal entre deux blocs de valeurs ; une valeur vide d'un seul côté compte comme infinie."""
    x, y = a.astype(float).to_numpy(), b.astype(float).to_numpy()
    gap = np.where(np.isnan(x) & np.isnan(y), 0.0, np.abs(x - y))
    return float(np.nan_to_num(gap, nan=np.inf).max()) if gap.size else 0.0


def _following_day(day, on_day, live, complete, features, model) -> dict:
    """Un jour suivant de la répétition : règle par championnat, règle par équipe, écart à l'historique complété."""
    from foot_predictor.inference.availability import AVAILABLE, match_availability, teams_busy_between

    seen, full = rows_for_day(live.matches, day), rows_for_day(complete.matches, day)
    elo = [c for c in features if c.startswith(("elo", "opp_elo"))]
    g2 = [c for c in features if c.startswith(("goals_", "opp_goals_", "xgp_", "opp_xgp_"))]
    counts = {
        "day": day.isoformat(), "matches": 0, "league_rule": 0, "team_rule": 0, "elo_identical": 0,
        "max_g2_gap": 0.0, "max_lambda_gap": None, "max_over_gap": None,
    }  # fmt: skip
    for _, match in on_day.iterrows():
        fresh = live.freshness.get(int(match["api_league_id"]))
        rows = seen[seen["match_id"] == match["match_id"]].sort_values("team_id").reset_index(drop=True)
        counts["matches"] += 1
        counts["league_rule"] += match_availability(match, rows, features, fresh).status == AVAILABLE
        teams = (match["home_team_id"], match["away_team_id"])
        busy = {str(k): v for k, v in teams_busy_between(live.matches, teams, fresh.complete_until, day).items()}
        if match_availability(match, rows, features, fresh, busy=busy).status != AVAILABLE:
            continue
        counts["team_rule"] += 1
        truth = full[full["match_id"] == match["match_id"]].sort_values("team_id").reset_index(drop=True)
        counts["elo_identical"] += len(truth) == len(rows) and _gap(rows[elo], truth[elo]) == 0.0
        counts["max_g2_gap"] = max(counts["max_g2_gap"], _gap(rows[g2], truth[g2]))
        if model is not None:
            a, b = model.predict(rows), model.predict(truth)
            lam = float(max(np.abs(a.lambda_home - b.lambda_home).max(), np.abs(a.lambda_away - b.lambda_away).max()))
            over = float(np.abs(a.total[:, :3].sum(axis=1) - b.total[:, :3].sum(axis=1)).max())
            counts["max_lambda_gap"] = max(counts["max_lambda_gap"] or 0.0, lam)
            counts["max_over_gap"] = max(counts["max_over_gap"] or 0.0, over)
    return counts


def render_live(report: dict) -> str:
    statuses = ", ".join(f"{k} {v}" for k, v in sorted(report["statuses"].items()))
    lines = [
        f"# Répétition du live sur la période de développement — {report['date']}",
        "",
        "Produit par `python -m foot_predictor.inference check --only live` (sous-étape 5.10, ADR-0042). Gel simulé au "
        f"{report['freeze']}, « aujourd'hui » simulé {report['today']} : les CSV historiques de football-data de la "
        "saison, coupés aux matchs d'avant ce jour, complètent la table gelée (superposition en mémoire).",
        "",
        f"- Matchs des 10 championnats entre le gel et ce jour : {report['matches_after_freeze']} ; résultats "
        f"rétablis par football-data : **{report['results_restored']}** ; scores différents de l'API : "
        f"**{report['score_mismatches']}**.",
        f"- Lignes inutilisables (jamais devinées) : {len(report['issues'])}.",
        f"- Lignes des matchs du {report['today']} : {report['rows']} ; buts et Elo identiques à ceux de la vraie "
        f"table : **{'oui' if report['goals_and_elo_identical'] else 'NON'}**.",
        f"- Statuts de disponibilité des matchs du jour : {statuses}.",
        f"- Durée de la superposition : {report['overlay_seconds']:.1f} s.",
        "",
        "| Variable en écart (tirs de football-data au lieu de ceux de l'API) | Lignes |",
        "|---|---|",
    ]
    lines += [f"| `{c}` | {n} |" for c, n in sorted(report["differing_columns"].items())] or ["| aucune | 0 |"]
    freshness = ", ".join(f"{k} : {v}" for k, v in sorted(report["freshness"].items()))
    lines += ["", f"Fraîcheur par championnat (identifiant API : complet jusqu'au) : {freshness}."]
    if report.get("following"):
        tol = report["tolerances"]
        verdict = "conforme" if report["following_ok"] else "NON CONFORME"
        lines += [
            "",
            "**Jours suivants, sans leurs résultats (fraîcheur par équipe, ADR-0046)** : comparaison avec la même "
            "superposition complétée des résultats manquants ; Elo identique attendu, écart de λ au plus "
            f"{tol['lambda']} et de P(T > 2,5) au plus {tol['p_over_2_5']} : **{verdict}**.",
            "",
            "| Jour | Matchs du top 5 | Disponibles (par championnat) | Disponibles (par équipe) | Elo identique "
            "| Écart max. G2 | Écart max. λ | Écart max. P(T > 2,5) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        fmt = lambda v: "—" if v is None else f"{v:.1e}"  # noqa: E731
        lines += [
            f"| {d['day']} | {d['matches']} | {d['league_rule']} | {d['team_rule']} | {d['elo_identical']} | "
            f"{fmt(d['max_g2_gap'])} | {fmt(d['max_lambda_gap'])} | {fmt(d['max_over_gap'])} |"
            for d in report["following"]
        ]
    if report["issues"]:
        lines += ["", "Lignes inutilisables :", ""]
        lines += [f"- {i['division']} {i['date']} : {i['reason']}" for i in report["issues"][:20]]
    return "\n".join(lines) + "\n"


def _api_to_internal() -> dict[int, int]:
    from foot_predictor.db.session import get_engine
    from foot_predictor.inference.context import api_to_internal

    return api_to_internal(get_engine())
