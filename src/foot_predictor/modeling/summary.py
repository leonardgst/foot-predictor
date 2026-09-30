"""Tableaux Markdown d'un rapport d'expérience (`reports/experiments/<id>.json`), pour `docs/resultats/`.

    uv run python -m foot_predictor.modeling summary reports/experiments/<id>.json

Les chiffres des pages de résultats sont **générés** à partir du rapport, jamais recopiés à la
main : une page et son rapport ne peuvent pas diverger.
"""

from __future__ import annotations

import json
from pathlib import Path


def _f(value, digits: int = 4, sign: bool = False) -> str:
    if value is None or value != value:  # NaN
        return "n. d."
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def _pct(value) -> str:
    return "n. d." if value is None else f"{100 * value:.1f} %"


def render(report: dict) -> str:
    """Tableaux : plis et matchs, métriques par pli, métriques poolées, sous-ensemble plus/moins 2,5, écarts."""
    lines = [
        f"Rapport `{report['id']}` : jeu `{report.get('dataset', {}).get('version')}`, commit "
        f"`{(report.get('git', {}).get('commit') or '')[:7]}`, graine {report['seed']}, "
        f"{report['n_resamples']} rééchantillonnages.",
        "",
        "| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |",
        "|---|---|---|---|---|---|",
    ]
    for fold in report["folds"]:
        params = "; ".join(f"{m} : {v['params']}" for m, v in fold["models"].items() if v["params"]) or "aucun"
        lines.append(
            f"| {fold['name']} | {fold['eval_matches']} | {fold['intersection']} | {fold['excluded_by_intersection']} "
            f"| {fold.get('over_2_5_matches', 'n. d.')} | {params} |"
        )
    lines += [
        "",
        "| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée "
        "| Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, per in report["metrics"].items():
        for fold, m in per.items():
            if "log_loss" not in m:
                continue
            cal, cov = m["calibration_over_2_5"], m["coverage_q10_q90"]
            lines.append(
                f"| {model} | {fold} | {_f(m['log_loss'])} | {_f(m['rps'])} | {_f(m['brier_over_2_5'])} "
                f"| {_f(cal['mean_abs_gap'])} | {_f(cal['slope'], 2)} | {_pct(cov['observed'])} | {_pct(cov['announced'])} "
                f"| {_f(m.get('exact_score_log_loss'))} | {_f(m.get('brier_1x2'))} "
                f"| {_f(m['descriptive']['mae_expected_total'], 3)} |"
            )
    lines += [
        "",
        "| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, p in report["pooled"].items():
        if "log_loss" not in p:
            continue
        cal = p["calibration_over_2_5"]
        lines.append(
            f"| {model} | {p['matches']} | {_f(p['log_loss'])} | {_f(p['rps'])} | {_f(p['brier_over_2_5'])} "
            f"| {_f(cal['mean_abs_gap'])} | {_f(cal['slope'], 2)} | {_f(cal['intercept'], 3, sign=True)} |"
        )
    subset = [(m, per) for m, per in report["metrics"].items() if any("over_2_5_subset" in v for v in per.values())]
    if subset:
        lines += [
            "",
            "Événement plus/moins 2,5, sur les matchs de l'intersection qui ont une cote :",
            "",
            "| Modèle | Pli | Matchs | Brier | Log-loss binaire | Calibration : écart moyen |",
            "|---|---|---|---|---|---|",
        ]
        for model, per in subset:
            for fold, m in per.items():
                o = m.get("over_2_5_subset")
                if o:
                    lines.append(
                        f"| {model} | {fold} | {o['matches']} | {_f(o['brier'])} | {_f(o['log_loss'])} "
                        f"| {_f(o['mean_abs_gap'])} |"
                    )
            pooled = report["pooled"].get(model, {}).get("brier_over_2_5_subset")
            lines.append(f"| {model} | **poolé** | | **{_f(pooled)}** | | |")
    lines += [
        "",
        "Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :",
        "",
        "| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |",
        "|---|---|---|---|---|---|---|---|",
    ]
    names = {"log_loss": "log-loss du total", "rps": "RPS", "brier_over_2_5_subset": "Brier plus/moins 2,5"}
    for item in report["comparisons"]:
        for key, label in names.items():
            if key not in item:
                continue
            x, p = item[key], item[key]["pooled"]
            per_fold = " ; ".join(f"{s} : {_f(v['mean'], sign=True)}" for s, v in x["per_fold"].items())
            lines.append(
                f"| {item['a']} | {item['b']} | {label} | {_f(p['mean'], 5, sign=True)} "
                f"| [{_f(p['low'], 5, sign=True)} ; {_f(p['high'], 5, sign=True)}] | {x['positive_folds']} sur "
                f"{len(x['per_fold'])} | {_f(x['diebold_mariano']['p_value'], 4)} | {per_fold} |"
            )
        if "decision" in item:
            d = item["decision"]
            lines.append(
                f"| | | règle de décision | (i) {'oui' if d['i_gain_significant'] else 'non'}, (ii) "
                f"{'oui' if d['ii_positive_folds'] else 'non'}, (iii) {'oui' if d['iii_calibration'] else 'non'} "
                f"| **{item['b']} {'remplace' if d['b_replaces_a'] else 'ne remplace pas'} {item['a']}** | | | |"
            )
    return "\n".join(lines) + "\n"


def summarize(path: Path) -> str:
    return render(json.loads(Path(path).read_text(encoding="utf-8")))
