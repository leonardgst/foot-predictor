"""Contrôles sur données réelles (`python -m foot_predictor.inference check`), rapport dans `reports/inference/`.

Les données locales (table des matchs de `staging`, jeu versionné) manquent en CI : ces contrôles
sont donc une commande, et non des tests automatisés (ADR-0040). Ils ne lisent que la période de
développement (porte `features/sources.py`).

Contrôle des lignes (décision 2, test (a)) : pour un échantillon de jours des quatre saisons de
validation et des cas limites (première journée d'une saison et ses promus, Ligue 1 à 18 clubs,
huis clos), les lignes d'inférence du jour doivent être **identiques au bit près** aux lignes du
jeu d'entraînement pour les mêmes matchs, toutes colonnes sauf celles d'après-match.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd

from foot_predictor.inference.rows import POST_MATCH_COLUMNS, rows_for_day

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports" / "inference"
DATASET_VERSION = "ds-2026-09-30-ba2b91f7"


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


def run_rows_check(matches: pd.DataFrame | None = None, dataset: pd.DataFrame | None = None) -> dict:
    from foot_predictor.features.sources import load_dataset, load_matches

    if matches is None:
        matches = load_matches()
    if dataset is None:
        dataset, _ = load_dataset(DATASET_VERSION)
    results = []
    for day, reason in sample_days(dataset):
        result = compare_day(matches, dataset, day)
        result["reason"] = reason
        results.append(result)
    return {
        "dataset": DATASET_VERSION,
        "days": results,
        "all_identical": all(r["identical"] for r in results),
        "rows_compared": sum(r["rows"] for r in results),
    }


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
