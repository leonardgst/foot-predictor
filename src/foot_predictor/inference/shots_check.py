"""Effet sur les prédictions d'un historique dont les tirs viennent de football-data (décision 12, ADR-0035).

Après le gel, les matchs joués n'auront que les tirs de football-data (ADR-0011), alors que le modèle
apprend sur un historique où les tirs viennent d'API-FOOTBALL depuis 2015-16 (ADR-0035). Les deux
sources ne coïncident que sur 72 % des matchs du top 5. Combien cela coûte-t-il ?

**Méthode figée** (décision 12 de la partie 5), pour chaque pli S (2021-22 à 2024-25), même modèle
(celui du rejeu de S, appris sur l'historique réel), même jeu :

- **référence** : les lignes du jeu `ds-2026-09-30-ba2b91f7` (tirs de l'API là où elle est complète) ;
- **variante « saison S »** : les matchs de la saison S perdent leurs tirs de l'API avant `build_frame`
  (ils prennent donc ceux de football-data) ; c'est la situation du live, où seule la saison en cours
  vient de football-data ;
- **variante extrême** : football-data pour toute l'histoire.

Mesure : écart de log-loss du total apparié match par match, variante moins référence (positif : la
variante est **moins bonne**), intervalle à 95 % par bootstrap par blocs de journées
(`modeling.bootstrap`, importé), par pli, poolé et par championnat. Ces mesures ne vont **pas** dans
`experiments/` (figé) : elles écrivent dans `reports/inference/`.

Critère de révision de l'ADR-0035 : un écart significatif ⇒ recalibration des tirs de football-data sur
ceux de l'API, par championnat, dans `inference/` (jamais dans `features/`), et nouvelle ADR. « Significatif »
est lu ainsi (ADR-0041) : intervalle poolé qui exclut 0, ou championnat dont la p-valeur de Diebold-Mariano,
corrigée de Holm sur les 5 championnats de la variante, est sous 5 %. La correction évite qu'un championnat
sur dix franchisse le seuil par le seul hasard des comparaisons multiples.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.features import huis_clos, xg_proxy
from foot_predictor.features.dataset import build_frame, load_elo_params
from foot_predictor.inference.models import replay_model
from foot_predictor.modeling import bootstrap, metrics, protocol

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_JSON = REPO_ROOT / "reports" / "inference" / "tirs_football_data.json"
REPORT_MD = REPO_ROOT / "docs" / "resultats" / "tirs_live.md"
API_SHOT_COLUMNS = ("home_shots_api", "home_sot_api", "away_shots_api", "away_sot_api")
SEASONS = (2021, 2022, 2023, 2024)
SEED = 20260930
N_RESAMPLES = 10_000
LEAGUES = {39: "Premier League", 140: "La Liga", 78: "Bundesliga", 135: "Serie A", 61: "Ligue 1"}


def without_api_shots(matches: pd.DataFrame, seasons=None) -> pd.DataFrame:
    """Copie de la table des matchs où les tirs de l'API sont retirés (des `seasons`, ou de tout l'historique)."""
    changed = matches.copy()
    mask = changed["season_year"].isin(list(seasons)) if seasons is not None else np.ones(len(changed), bool)
    for column in API_SHOT_COLUMNS:
        changed[column] = changed[column].astype("Float64")
        changed.loc[mask, column] = pd.NA
    return changed


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """P-valeurs corrigées de Holm (pas à pas descendant, monotones, plafonnées à 1)."""
    clean = {name: (1.0 if p != p else p) for name, p in p_values.items()}  # p vide (aucun écart) : 1
    ordered = sorted(clean.items(), key=lambda item: item[1])
    adjusted, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[name] = running
    return adjusted


def source_gap(matches: pd.DataFrame, seasons=SEASONS) -> dict:
    """Écart des tirs cadrés football-data − API par équipe et par match, matchs où les deux sont complets.

    Diagnostic du mécanisme, sur les seules saisons de développement (la table vient de `sources.py`).
    """
    frame = matches[matches["season_year"].isin(list(seasons))]
    out = {}
    for code, name in LEAGUES.items():
        league = frame[frame["api_league_id"] == code]
        api = pd.concat([league["home_sot_api"], league["away_sot_api"]]).astype("Float64")
        fd = pd.concat([league["home_sot_fd"], league["away_sot_fd"]]).astype("Float64")
        both = api.notna() & fd.notna()
        gap = (fd[both] - api[both]).astype(float)
        if not both.any():
            continue
        out[name] = {
            "team_matches": int(both.sum()),
            "mean_gap": round(float(gap.mean()), 4),
            "mean_abs_gap": round(float(gap.abs().mean()), 4),
            "share_equal": round(float((gap == 0).mean()), 4),
        }
    return out


def changed_share(reference: pd.DataFrame, variant: pd.DataFrame, features: list[str]) -> float:
    """Part des lignes de test dont au moins une variable du modèle change entre les deux sources."""
    left = reference.set_index(["match_id", "team_id"])[features]
    right = variant.set_index(["match_id", "team_id"])[features].loc[left.index]
    differs = ~np.isclose(left.to_numpy(float), right.to_numpy(float), rtol=0, atol=1e-12, equal_nan=True)
    return round(float(differs.any(axis=1).mean()), 4)


def season_losses(model, rows: pd.DataFrame, truth: pd.DataFrame) -> pd.Series:
    """Log-loss du total par match (index : match_id) des lignes utilisables et complètes."""
    usable, _ = protocol.usable(rows, model.features)
    predicted = model.predict(protocol.complete_matches(usable))
    totals = truth.loc[predicted.match_id, "total"].to_numpy()
    return pd.Series(metrics.log_loss_by_match(predicted.total, totals), index=predicted.match_id)


def run(
    matches: pd.DataFrame | None = None,
    dataset: pd.DataFrame | None = None,
    manifest: dict | None = None,
    *,
    seasons=SEASONS,
    model_for=None,
    build=None,
    n_resamples: int = N_RESAMPLES,
) -> dict:
    """Mesure complète. Par défaut : table des matchs et jeu réels (porte `sources.py`), modèles de rejeu.

    `model_for(season)` et `build(matches)` sont injectables pour les tests (données synthétiques).
    """
    from foot_predictor.features.sources import load_dataset, load_matches

    if matches is None:
        matches = load_matches()
    if dataset is None:
        dataset, manifest = load_dataset("ds-2026-09-30-ba2b91f7")
    if build is None:
        params, coefficients, periods = load_elo_params(), xg_proxy.load(), huis_clos.load_periods()
        build = lambda frame: build_frame(frame, params, coefficients, periods)  # noqa: E731
    if model_for is None:
        model_for = lambda season: replay_model(season, dataset, manifest).model  # noqa: E731
    started = time.perf_counter()
    extreme = build(without_api_shots(matches))
    variants: dict[str, dict] = {"saison_S": {}, "toute_histoire": {}}
    changed: dict[str, dict] = {"saison_S": {}, "toute_histoire": {}}
    baseline: dict[int, pd.Series] = {}
    truths: dict[int, pd.DataFrame] = {}
    for season in seasons:
        model = model_for(season)
        truths[season] = truth = protocol.outcomes(dataset, season)
        reference = protocol.test_rows(dataset, season)
        baseline[season] = season_losses(model, reference, truth)
        season_frame = build(without_api_shots(matches, [season]))
        for name, frame in (("saison_S", season_frame), ("toute_histoire", extreme)):
            rows = protocol.test_rows(frame, season)
            variants[name][season] = season_losses(model, rows, truth)
            changed[name][str(season)] = changed_share(reference, rows, list(model.features))
    report = {
        "date": dt.datetime.now(dt.UTC).date().isoformat(),
        "dataset": (manifest or {}).get("version"),
        "seed": SEED,
        "n_resamples": n_resamples,
        "trials": 1,
        "method": "variante − référence, log-loss du total apparié ; positif : la variante est moins bonne",
        "source_gap": {
            f"{min(seasons)}-{max(seasons)}": source_gap(matches, seasons),
            f"2015-{max(seasons)}": source_gap(matches, range(2015, max(seasons) + 1)),
        },
        "variants": {},
    }
    for name, by_season in variants.items():
        compared = compare_variant(baseline, by_season, truths, n_resamples)
        report["variants"][name] = compared | {"changed_rows": changed[name]}
    report["seconds"] = round(time.perf_counter() - started, 1)
    return report


def compare_variant(baseline: dict, variant: dict, truths: dict, n_resamples: int = N_RESAMPLES) -> dict:
    """Écarts appariés sur les matchs prédits des deux côtés : par pli, poolé, par championnat."""
    diffs, blocks, strata, leagues, counts = [], [], [], [], {}
    for season, base in baseline.items():
        common = base.index.intersection(variant[season].index)
        counts[str(season)] = {"common": int(len(common)), "baseline": int(len(base)),
                               "variant": int(len(variant[season]))}  # fmt: skip
        truth = truths[season].loc[common]
        diffs.append((variant[season].loc[common] - base.loc[common]).to_numpy())
        blocks.append(bootstrap.block_keys(truth).to_numpy())
        strata.append(np.full(len(common), season))
        leagues.append(truth["api_league_id"].to_numpy())
    diff, block, stratum, league = map(np.concatenate, (diffs, blocks, strata, leagues))
    pooled = bootstrap.block_bootstrap(diff, block, stratum, n_resamples=n_resamples, seed=SEED)
    per_fold = {
        str(s): bootstrap.block_bootstrap(d, b, n_resamples=n_resamples, seed=SEED + int(s)).to_dict()
        for s, d, b in zip(baseline, diffs, blocks, strict=True)
    }
    per_league = {}
    for code, name in LEAGUES.items():
        mask = league == code
        if not mask.any():
            continue
        interval = bootstrap.block_bootstrap(diff[mask], block[mask], stratum[mask], n_resamples=n_resamples, seed=SEED)
        per_league[name] = interval.to_dict() | {
            "excludes_zero": interval.excludes_zero(),
            "dm_p_value": bootstrap.diebold_mariano(diff[mask], block[mask])["p_value"],
        }
    adjusted = holm({name: v["dm_p_value"] for name, v in per_league.items()})
    for name, value in adjusted.items():
        per_league[name]["holm_p_value"] = value
    significant = pooled.excludes_zero() or any(p < 0.05 for p in adjusted.values())
    return {
        "significant": significant,
        "pooled": pooled.to_dict() | {"excludes_zero": pooled.excludes_zero()},
        "per_fold": per_fold,
        "per_league": per_league,
        "matches": counts,
        "diebold_mariano": bootstrap.diebold_mariano(diff, block),
    }


def render(report: dict) -> str:
    seasons = [int(s) for s in next(iter(report["variants"].values()))["per_fold"]]
    labels = {
        "saison_S": "Saison S en football-data (situation du live)",
        "toute_histoire": "Football-data pour toute l'histoire (extrême)",
    }
    lines = [
        "# Tirs de football-data en live : effet sur les prédictions",
        "",
        f"*Mesure du {report['date']} (décision 12 de la partie 5, ADR-0035). Jeu `{report['dataset']}`, modèles de "
        f"rejeu des 4 plis, {report['n_resamples']} rééchantillonnages, graine {report['seed']}, {report['trials']} "
        "essai. Produit par `python -m foot_predictor.inference.shots_check` ; données dans "
        "`reports/inference/tirs_football_data.json`.*",
        "",
        "Écart = log-loss du total avec la variante − log-loss avec les tirs de référence (API là où elle est complète), "
        "même modèle, mêmes matchs. **Positif : la variante est moins bonne.**",
        "",
        "| Variante | Écart poolé | IC 95 % | Exclut 0 | DM (p) | "
        + " | ".join(f"{s}-{(s + 1) % 100:02d}" for s in seasons)
        + " |",
        "|---|---|---|---|---|" + "---|" * len(seasons),
    ]
    for name, v in report["variants"].items():
        p = v["pooled"]
        folds = " | ".join(f"{v['per_fold'][str(s)]['mean']:+.5f}" for s in seasons)
        lines.append(f"| {labels[name]} | {p['mean']:+.5f} | [{p['low']:+.5f} ; {p['high']:+.5f}] | "
                     f"{'oui' if p['excludes_zero'] else 'non'} | {v['diebold_mariano']['p_value']:.3f} | {folds} |")  # fmt: skip
    lines += [
        "",
        "Par championnat :",
        "",
        "| Variante | Championnat | Écart | IC 95 % | Exclut 0 | DM (p) | Holm (p) |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, v in report["variants"].items():
        for league, i in v["per_league"].items():
            lines.append(f"| {labels[name]} | {league} | {i['mean']:+.5f} | [{i['low']:+.5f} ; {i['high']:+.5f}] | "
                         f"{'oui' if i['excludes_zero'] else 'non'} | {i['dm_p_value']:.3f} | {i['holm_p_value']:.3f} |")  # fmt: skip
    lines += ["", "Matchs comparés et part des lignes de test dont une variable du modèle change :", ""]
    lines += ["| Variante | Pli | Communs | Référence | Variante | Lignes changées |", "|---|---|---|---|---|---|"]
    for name, v in report["variants"].items():
        for season, c in v["matches"].items():
            lines.append(f"| {labels[name]} | {season} | {c['common']} | {c['baseline']} | {c['variant']} | "
                         f"{v['changed_rows'][season]:.1%} |")  # fmt: skip
    lines += [
        "",
        "Écart des sources (tirs cadrés football-data − API, par équipe et par match, quand les deux sont complets) :",
        "",
        "| Saisons | Championnat | Équipe-matchs | Écart moyen | Écart absolu moyen | Identiques |",
        "|---|---|---|---|---|---|",
    ]
    for period, gaps in report["source_gap"].items():
        for league, g in gaps.items():
            lines.append(f"| {period} | {league} | {g['team_matches']} | {g['mean_gap']:+.3f} | "
                         f"{g['mean_abs_gap']:.3f} | {g['share_equal']:.1%} |")  # fmt: skip
    significant = [labels[n] for n, v in report["variants"].items() if v["significant"]]
    lines += [
        "",
        "## Conclusion",
        "",
        "Critère (ADR-0041) : intervalle poolé qui exclut 0, ou championnat dont la p-valeur de Diebold-Mariano "
        "corrigée de Holm (5 championnats) est sous 5 %.",
        "",
    ]
    if significant:
        lines.append(f"**Écart significatif** ({', '.join(significant)}) : critère de révision de l'ADR-0035 atteint.")
    else:
        lines.append("**Aucun écart significatif** : le critère de révision de l'ADR-0035 n'est pas atteint ; les tirs "
                     "de football-data sont utilisés tels quels en live (constat chiffré, ADR-0041).")  # fmt: skip
    return "\n".join(lines) + "\n"


def main() -> int:
    report = run()
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    REPORT_MD.write_text(render(report), encoding="utf-8", newline="\n")
    for name, v in report["variants"].items():
        p = v["pooled"]
        print(f"{name} : {p['mean']:+.5f} [{p['low']:+.5f} ; {p['high']:+.5f}]")
    print(f"Rapport : {REPORT_MD} ({report['seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
