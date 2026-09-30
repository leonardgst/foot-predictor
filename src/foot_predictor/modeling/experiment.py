"""Exécuteur d'expériences : `experiments/<nom>.yaml` → `reports/experiments/<id>.json` (rapport F.4, I.7).

    uv run python -m foot_predictor.modeling evaluate experiments/<nom>.yaml

Une expérience décrit : le jeu de données (version), les plis, la population d'apprentissage,
les modèles (et leur grille d'hyperparamètres), la graine et le nombre de rééchantillonnages,
et les comparaisons (A, B) à chiffrer. L'exécuteur :

1. lit le jeu par la porte (`features/sources.load_dataset`, scellé vérifié) ;
2. pour chaque modèle et chaque pli : validation interne, ajustement, prédiction des matchs de
   test (`protocol`) ;
3. restreint chaque pli à l'**intersection** des matchs prédits par tous les modèles à loi
   complète, et publie le nombre de matchs écartés ;
4. calcule les métriques (ADR-0009) par pli et poolées, et les écarts appariés avec leur
   intervalle par bootstrap de blocs et le test de Diebold-Mariano (`bootstrap`) ;
5. écrit le rapport JSON, les prédictions par match (`data/experiments/<id>/`, ignoré par Git)
   et régénère `reports/experiments/INDEX.md`.

**Tous les essais sont conservés**, y compris ceux qui échouent (statut « échec » et message) :
l'index en donne le nombre, pour se méfier des comparaisons multiples.

Le marché (`market`) ne donne que P(T > 2,5) : il n'entre pas dans l'intersection des lois
complètes et n'est comparé que sur l'événement plus/moins 2,5, sur l'intersection de ses matchs
avec ceux des autres modèles.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import subprocess
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from foot_predictor.modeling import bootstrap, metrics, protocol
from foot_predictor.modeling.models import MODELS

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports" / "experiments"
PREDICTIONS_DIR = REPO_ROOT / "data" / "experiments"
INDEX_PATH = REPORTS_DIR / "INDEX.md"
ROUND_BUCKETS = ((1, 5), (6, 10), (11, 19), (20, 99))
"""Tranches de journées (rapport H.4) : début de saison, puis le reste."""


class ExperimentError(ValueError):
    """Fichier d'expérience invalide."""


# ------------------------------------------------------------------------------ lecture


def load_spec(path: Path) -> dict:
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for key in ("name", "models"):
        if key not in spec:
            raise ExperimentError(f"{path} : clé « {key} » manquante")
    spec.setdefault("dataset", None)
    spec.setdefault("folds", list(protocol.TEST_SEASONS))
    spec.setdefault("population", "top5")
    spec.setdefault("seed", 20260930)
    spec.setdefault("n_resamples", bootstrap.N_RESAMPLES)
    spec.setdefault("comparisons", [])
    ids = [m["id"] for m in spec["models"]]
    if len(set(ids)) != len(ids):
        raise ExperimentError(f"{path} : identifiants de modèles en double")
    for model in spec["models"]:
        if model["model"] not in MODELS and model["model"] != "market":
            raise ExperimentError(f"{path} : modèle inconnu « {model['model']} »")
    for a, b in spec["comparisons"]:
        if a not in ids or b not in ids:
            raise ExperimentError(f"{path} : comparaison {a} / {b} sur un modèle absent")
    return spec


def expand_grid(grid: dict | None) -> list[dict]:
    """{"a": [1, 2], "b": [3]} → [{"a": 1, "b": 3}, {"a": 2, "b": 3}] ; sans grille : [{}]."""
    if not grid:
        return [{}]
    keys = sorted(grid)
    return [dict(zip(keys, values, strict=True)) for values in itertools.product(*(grid[k] for k in keys))]


# ------------------------------------------------------------------------------ métriques


def round_number(rounds: pd.Series) -> pd.Series:
    """« Regular Season - 12 » → 12 ; vide sinon."""
    return pd.to_numeric(rounds.astype("string").str.extract(r"(\d+)\s*$")[0], errors="coerce")


def distribution_metrics(predicted, truth: pd.DataFrame, rng: np.random.Generator) -> dict:
    """Toutes les métriques d'une loi complète du total sur des matchs donnés (mêmes ordres)."""
    totals = truth["total"].to_numpy()
    over = totals > 2.5
    p_over = metrics.prob_over(predicted.total)
    table = metrics.calibration_table(p_over, over)
    intercept, slope = metrics.calibration_slope_intercept(p_over, over)
    result = {
        "matches": int(len(totals)),
        "log_loss": float(metrics.log_loss_by_match(predicted.total, totals).mean()),
        "rps": float(metrics.rps_by_match(predicted.total, totals).mean()),
        "brier_over_2_5": float(metrics.brier_over_by_match(predicted.total, totals).mean()),
        "calibration_over_2_5": {
            "table": table.round(6).to_dict(orient="records"),
            "mean_abs_gap": metrics.calibration_mean_abs_gap(table),
            "intercept": intercept,
            "slope": slope,
        },
        "pit_histogram": metrics.pit_histogram(metrics.randomized_pit(predicted.total, totals, rng)).tolist(),
        "coverage_q10_q90": metrics.coverage(predicted.total, totals),
    }
    mae, rmse = metrics.mae_rmse(predicted.lambda_home + predicted.lambda_away, totals)
    result["descriptive"] = {"mae_expected_total": mae, "rmse_expected_total": rmse}
    if predicted.home is not None and predicted.away is not None:
        home = metrics.log_loss_by_match(_fold(predicted.home), truth["home_goals"].to_numpy())
        away = metrics.log_loss_by_match(_fold(predicted.away), truth["away_goals"].to_numpy())
        result["team_log_loss"] = {"home": float(home.mean()), "away": float(away.mean())}
    if predicted.joint is not None:
        from foot_predictor.modeling import distributions as dist

        result["exact_score_log_loss"] = float(
            metrics.exact_score_log_loss_by_match(predicted.joint, truth["home_goals"], truth["away_goals"]).mean()
        )
        result["brier_1x2"] = float(
            metrics.brier_1x2_by_match(
                dist.outcome_probabilities(predicted.joint), truth["home_goals"], truth["away_goals"]
            ).mean()
        )
    if predicted.extra:
        # Diagnostics propres au modèle, par match (M1 : masse négative, borne basse < 0…) : moyennes du pli.
        result["extra"] = {name: float(np.mean(values)) for name, values in predicted.extra.items()}
    for k in (0, 1, 2):
        observed = (totals == k).astype(float)
        result.setdefault("small_totals", {})[str(k)] = {
            "predicted": float(predicted.total[:, k].mean()),
            "observed": float(observed.mean()),
            "brier": float(metrics.brier_binary_by_match(predicted.total[:, k], observed).mean()),
        }
    return result


def _fold(pmf: np.ndarray) -> np.ndarray:
    from foot_predictor.modeling import distributions as dist

    return dist.fold(pmf)


def compare(losses_a: dict, losses_b: dict, blocks: dict, n_resamples: int, seed: int) -> dict:
    """Écart apparié A − B (positif : B meilleur), poolé sur les plis et par pli, avec intervalles et DM."""
    seasons = sorted(losses_a)
    diff = np.concatenate([losses_a[s] - losses_b[s] for s in seasons])
    block = np.concatenate([blocks[s] for s in seasons])
    strata = np.concatenate([np.full(len(blocks[s]), s) for s in seasons])
    pooled = bootstrap.block_bootstrap(diff, block, strata, n_resamples=n_resamples, seed=seed)
    per_fold = {}
    for s in seasons:
        interval = bootstrap.block_bootstrap(
            losses_a[s] - losses_b[s], blocks[s], n_resamples=n_resamples, seed=seed + int(s)
        )
        per_fold[str(s)] = interval.to_dict()
    return {
        "pooled": pooled.to_dict() | {"excludes_zero": pooled.excludes_zero()},
        "per_fold": per_fold,
        "positive_folds": int(sum(v["mean"] > 0 for v in per_fold.values())),
        "diebold_mariano": bootstrap.diebold_mariano(diff, block),
    }


def git_state() -> dict:
    def run(*args):
        try:
            done = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ""
        return done.stdout

    return {
        "commit": run("rev-parse", "HEAD").strip() or None,
        "dirty": bool(run("status", "--porcelain", "--untracked-files=no").strip()),
    }


def run_experiment(
    path: Path,
    reports_dir: Path = REPORTS_DIR,
    predictions_dir: Path = PREDICTIONS_DIR,
    data: pd.DataFrame | None = None,
    manifest: dict | None = None,
    now: dt.datetime | None = None,
    odds: pd.DataFrame | None = None,
) -> dict:
    """Exécute une expérience ; écrit toujours un rapport, même en cas d'échec (statut « échec »)."""
    path = Path(path)
    spec = load_spec(path)
    now = now or dt.datetime.now(dt.UTC)
    experiment_id = f"{spec['name']}-{now:%Y%m%dT%H%M%S}"
    report: dict = {
        "id": experiment_id,
        "name": spec["name"],
        "experiment_file": path.as_posix(),
        "date": now.isoformat(timespec="seconds"),
        "git": git_state(),
        "seed": spec["seed"],
        "n_resamples": spec["n_resamples"],
        "spec": spec,
        "status": "en cours",
    }
    try:
        if data is None:
            from foot_predictor.features.sources import load_dataset

            data, manifest = load_dataset(spec["dataset"])
        report["dataset"] = {
            "version": (manifest or {}).get("version"),
            "manifest_sha256": (manifest or {}).get("manifest_sha256"),
        }
        report.update(_execute(spec, data, predictions_dir / experiment_id, odds))
        report["status"] = "ok"
    except Exception as error:  # noqa: BLE001 - un essai qui échoue est conservé, pas caché
        report["status"] = "échec"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc(limit=5)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{experiment_id}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8"
    )
    write_index(reports_dir)
    return report


def _json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value))


def _execute(spec: dict, data: pd.DataFrame, predictions_dir: Path, odds: pd.DataFrame | None) -> dict:
    folds = protocol.folds(spec["folds"])
    full = [m for m in spec["models"] if m["model"] != "market"]
    markets = [m for m in spec["models"] if m["model"] == "market"]
    if markets:
        from foot_predictor.modeling.models import market  # référence de marché (sous-étape 4.5)

    if markets and odds is None:
        odds = market.load_market_probabilities()
    rng = np.random.default_rng(spec["seed"])
    fold_reports = []
    per_model: dict[str, dict] = {m["id"]: {} for m in spec["models"]}
    losses: dict[str, dict] = {m["id"]: {} for m in full}
    rps_losses: dict[str, dict] = {m["id"]: {} for m in full}
    over_losses: dict[str, dict] = {m["id"]: {} for m in spec["models"]}
    blocks, over_blocks, frames = {}, {}, []
    p_overs: dict[str, dict] = {}
    over_outcomes: dict[int, np.ndarray] = {}
    for fold in folds:
        truth_all = protocol.outcomes(data, fold.test_season)
        entry = {"season": fold.test_season, "name": fold.name, "eval_matches": int(len(truth_all)), "models": {}}
        predicted = {}
        for model_spec in full:
            make = MODELS[model_spec["model"]]
            fixed = model_spec.get("params") or {}
            grid = [fixed | g for g in expand_grid(model_spec.get("grid"))]
            features = make(**grid[0]).features
            population = model_spec.get("population", spec["population"])
            fit = protocol.select_and_fit(make, grid, data, fold, population, features)
            predictions, missing = protocol.predict_fold(fit, data, fold, features)
            predicted[model_spec["id"]] = predictions
            entry["models"][model_spec["id"]] = {
                "params": fit.params,
                "excluded_train_rows": fit.excluded_train_rows,
                "matches_without_prediction": missing,
                "inner_validation": fit.inner_scores,
                "fitted": fit.model.describe(),
            }
        common = protocol.intersection(predicted) if predicted else truth_all.index.to_numpy()
        entry["intersection"] = int(len(common))
        entry["excluded_by_intersection"] = int(len(truth_all) - len(common))
        truth = truth_all.loc[common]
        blocks[fold.test_season] = bootstrap.block_keys(truth).to_numpy()
        for model_id, predictions in predicted.items():
            sub = predictions.subset(common)
            per_model[model_id][fold.name] = distribution_metrics(sub, truth, rng)
            per_model[model_id][fold.name]["by_round"] = by_round(sub, truth)
            losses[model_id][fold.test_season] = metrics.log_loss_by_match(sub.total, truth["total"].to_numpy())
            p_overs.setdefault(model_id, {})[fold.test_season] = metrics.prob_over(sub.total)
            over_outcomes[fold.test_season] = (truth["total"].to_numpy() > 2.5).astype(float)
            rps_losses[model_id][fold.test_season] = metrics.rps_by_match(sub.total, truth["total"].to_numpy())
            frames.append(_prediction_frame(model_id, fold, sub, truth))
        if markets:
            # Marché : événement plus/moins 2,5 seulement, sur les matchs de l'intersection qui ont une cote.
            over_common = common
            for model_spec in markets:
                version = (model_spec.get("params") or {}).get("version", "avant_cloture")
                available = odds.loc[odds["version"] == version, "match_id"].to_numpy()
                over_common = np.intersect1d(over_common, available)
            entry["over_2_5_matches"] = int(len(over_common))
            entry["excluded_without_odds"] = int(len(common) - len(over_common))
            truth_over = truth_all.loc[over_common]
            over_blocks[fold.test_season] = bootstrap.block_keys(truth_over).to_numpy()
            outcome = (truth_over["total"].to_numpy() > 2.5).astype(float)
            for model_id, predictions in predicted.items():
                p = metrics.prob_over(predictions.subset(over_common).total)
                over_losses[model_id][fold.test_season] = metrics.brier_binary_by_match(p, outcome)
                per_model[model_id][fold.name]["over_2_5_subset"] = binary_metrics(p, outcome)
            for model_spec in markets:
                version = (model_spec.get("params") or {}).get("version", "avant_cloture")
                p = market.probabilities(odds, version, over_common)
                over_losses[model_spec["id"]][fold.test_season] = metrics.brier_binary_by_match(p, outcome)
                per_model[model_spec["id"]][fold.name] = {"over_2_5_subset": binary_metrics(p, outcome)}
        fold_reports.append(entry)

    pooled = {}
    for model_id, by_season in losses.items():
        seasons = sorted(by_season)
        p_over = np.concatenate([p_overs[model_id][s] for s in seasons])
        outcome = np.concatenate([over_outcomes[s] for s in seasons])
        table = metrics.calibration_table(p_over, outcome)
        intercept, slope = metrics.calibration_slope_intercept(p_over, outcome)
        pooled[model_id] = {
            "log_loss": float(np.concatenate([by_season[s] for s in seasons]).mean()),
            "rps": float(np.concatenate([rps_losses[model_id][s] for s in seasons]).mean()),
            "brier_over_2_5": float(metrics.brier_binary_by_match(p_over, outcome).mean()),
            "matches": int(sum(len(by_season[s]) for s in seasons)),
            # Critère (iii) de la règle de décision : calibration poolée sur les 4 plis (ADR-0037).
            "calibration_over_2_5": {
                "table": table.round(6).to_dict(orient="records"),
                "mean_abs_gap": metrics.calibration_mean_abs_gap(table),
                "intercept": intercept,
                "slope": slope,
            },
        }
    for model_id, by_season in over_losses.items():
        if by_season:
            seasons = sorted(by_season)
            pooled.setdefault(model_id, {})["brier_over_2_5_subset"] = float(
                np.concatenate([by_season[s] for s in seasons]).mean()
            )
    comparisons = []
    for a, b in spec["comparisons"]:
        item = {"a": a, "b": b}
        if a in losses and b in losses:
            item["log_loss"] = compare(losses[a], losses[b], blocks, spec["n_resamples"], spec["seed"])
            item["rps"] = compare(rps_losses[a], rps_losses[b], blocks, spec["n_resamples"], spec["seed"])
            item["calibration_pooled"] = {
                model_id: {
                    k: pooled[model_id]["calibration_over_2_5"][k] for k in ("mean_abs_gap", "slope", "intercept")
                }
                for model_id in (a, b)
            }
            item["decision"] = decision(item, pooled[a], pooled[b])
        if over_blocks and over_losses[a] and over_losses[b]:
            item["brier_over_2_5_subset"] = compare(
                over_losses[a], over_losses[b], over_blocks, spec["n_resamples"], spec["seed"]
            )
        comparisons.append(item)
    if frames:
        predictions_dir.mkdir(parents=True, exist_ok=True)
        pd.concat(frames, ignore_index=True).to_parquet(predictions_dir / "predictions.parquet", index=False)
    return {"folds": fold_reports, "metrics": per_model, "pooled": pooled, "comparisons": comparisons}


MAX_CALIBRATION_GAP_INCREASE = 0.005
"""Critère (iii) : l'écart absolu moyen par décile de P(T ≥ 3) n'augmente pas de plus de 0,5 point."""
SLOPE_RANGE = (0.9, 1.1)
"""Critère (iii) : la pente de calibration de B reste dans [0,9 ; 1,1]."""
MIN_POSITIVE_FOLDS = 3


def decision(item: dict, pooled_a: dict, pooled_b: dict) -> dict:
    """Règle de décision pré-enregistrée (ADR-0037) : B remplace A si (i), (ii) et (iii) sont vrais.

    (i) l'intervalle à 95 % du gain moyen de log-loss du total (A − B, 4 plis poolés) exclut 0 et
    le gain est positif ; (ii) le gain est positif dans au moins 3 plis sur 4 ; (iii) la
    calibration poolée de P(T ≥ 3) ne se dégrade pas (écart absolu moyen par décile + 0,5 point
    au plus, pente de B dans [0,9 ; 1,1]). Sinon, on garde A (le plus simple).
    """
    loss = item["log_loss"]
    gain_significant = loss["pooled"]["excludes_zero"] and loss["pooled"]["mean"] > 0
    folds_ok = loss["positive_folds"] >= MIN_POSITIVE_FOLDS
    gap_a = pooled_a["calibration_over_2_5"]["mean_abs_gap"]
    gap_b = pooled_b["calibration_over_2_5"]["mean_abs_gap"]
    slope_b = pooled_b["calibration_over_2_5"]["slope"]
    calibration_ok = gap_b - gap_a <= MAX_CALIBRATION_GAP_INCREASE and SLOPE_RANGE[0] <= slope_b <= SLOPE_RANGE[1]
    return {
        "i_gain_significant": bool(gain_significant),
        "ii_positive_folds": bool(folds_ok),
        "iii_calibration": bool(calibration_ok),
        "b_replaces_a": bool(gain_significant and folds_ok and calibration_ok),
    }


def by_round(predicted, truth: pd.DataFrame) -> dict:
    """Log-loss du total par tranche de journées (début de saison, rapport H.4) : descriptif."""
    number = round_number(truth["round"]).to_numpy() if "round" in truth.columns else np.full(len(truth), np.nan)
    loss = metrics.log_loss_by_match(predicted.total, truth["total"].to_numpy())
    result = {}
    for lo, hi in ROUND_BUCKETS:
        mask = (number >= lo) & (number <= hi)
        if mask.any():
            result[f"{lo}-{hi}"] = {"matches": int(mask.sum()), "log_loss": float(loss[mask].mean())}
    return result


def binary_metrics(p: np.ndarray, outcome: np.ndarray) -> dict:
    table = metrics.calibration_table(p, outcome)
    return {
        "matches": int(len(p)),
        "brier": float(metrics.brier_binary_by_match(p, outcome).mean()),
        "log_loss": float(metrics.log_loss_binary_by_match(p, outcome).mean()),
        "mean_abs_gap": metrics.calibration_mean_abs_gap(table),
        "table": table.round(6).to_dict(orient="records"),
    }


def _prediction_frame(model_id: str, fold: protocol.Fold, predicted, truth: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "model": model_id,
            "fold": fold.test_season,
            "match_id": predicted.match_id,
            "lambda_home": predicted.lambda_home,
            "lambda_away": predicted.lambda_away,
            "total": truth["total"].to_numpy(),
        }
    )
    for k in range(predicted.total.shape[1]):
        frame[f"p_total_{k}"] = predicted.total[:, k]
    return frame


# ------------------------------------------------------------------------------ index


def write_index(reports_dir: Path = REPORTS_DIR) -> Path:
    """Régénère `INDEX.md` : tous les essais, réussis ou non, et leur nombre."""
    rows = []
    for path in sorted(reports_dir.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        models = ", ".join(m["id"] for m in report.get("spec", {}).get("models", []))
        headline = ""
        for item in report.get("comparisons", []):
            if "log_loss" in item:
                p = item["log_loss"]["pooled"]
                headline = f"{item['a']} − {item['b']} : {p['mean']:+.4f} [{p['low']:+.4f} ; {p['high']:+.4f}]"
                break
        rows.append((report.get("date", ""), report["id"], report.get("status", "?"), models, headline))
    failed = sum(1 for row in rows if row[2] != "ok")
    lines = [
        "# Index des expériences (généré)",
        "",
        "Généré par `python -m foot_predictor.modeling evaluate` (ou `index`). **Tous les essais sont conservés**, "
        "y compris ceux qui échouent : leur nombre aide à se méfier des comparaisons multiples.",
        "",
        f"**{len(rows)} essai(s)**, dont {failed} en échec.",
        "",
        "| Date (UTC) | Identifiant | Statut | Modèles | Première comparaison (log-loss du total, A − B, poolée) |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {d} | `{i}` | {s} | {m} | {h} |" for d, i, s, m, h in sorted(rows)]
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "INDEX.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
