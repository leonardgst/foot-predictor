"""Rapport du live (`python -m foot_predictor.inference live`, 5.14 ; ADR-0011, ADR-0042).

Pour les prochains jours, à partir des réponses de `predict_day` en mode live : nombre de matchs du
top 5, disponibles ou non, raisons d'indisponibilité, références de marché, fraîcheur de chaque
championnat et lignes de football-data inutilisables. La **part d'indisponibles** se compare au
critère de révision de l'ADR-0011 : plus d'un match du top 5 sur cinq indisponible sur les premières
semaines de live.

Le rapport ne contient que des décomptes, des dates et des raisons : les prédictions elles-mêmes vont
dans `ops.prediction` (`--save`), avant le coup d'envoi. Seules les réponses **disponibles** y sont
écrites : l'écriture est idempotente par (match, modèle, horizon, mode), et une ligne « indisponible »
écrite trop tôt empêcherait d'écrire plus tard la prédiction devenue disponible.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter

from foot_predictor.inference.availability import AVAILABLE, OUT_OF_SCOPE

UNAVAILABLE_SHARE_LIMIT = 0.2
"""ADR-0011, critère de révision : plus d'un match du top 5 sur cinq indisponible."""


def reason_label(reason: str) -> str:
    """Raison sans son détail (variable, côté, date) : « variables d'historique périmées », etc."""
    return reason.split(" : ")[0].split(" (")[0].strip()


def summarize(answers_by_day: dict[dt.date, list[dict]], context) -> dict:
    """Résumé des réponses live jour par jour (matchs du périmètre du modèle seulement)."""
    days, reasons = [], Counter()
    total = available = with_market = 0
    for day in sorted(answers_by_day):
        in_scope = [a for a in answers_by_day[day] if a["status"] != OUT_OF_SCOPE]
        statuses = Counter(a["status"] for a in in_scope)
        for answer in in_scope:
            if answer["status"] != AVAILABLE:
                reasons.update({reason_label(r) for r in answer["reasons"]})
        days.append({"day": day.isoformat(), "matches": len(in_scope), "statuses": dict(statuses),
                     "out_of_scope": len(answers_by_day[day]) - len(in_scope)})  # fmt: skip
        total += len(in_scope)
        available += statuses.get(AVAILABLE, 0)
        with_market += sum(1 for a in in_scope if a.get("market_reference"))
    share = (total - available) / total if total else None
    versions = sorted({a["model_version"] for answers in answers_by_day.values() for a in answers})
    summary = context.live_summary or {}
    return {
        "today": context.today.isoformat() if context.today else None,
        "data_version": context.data_version,
        "model_versions": versions,
        "matches": total,
        "available": available,
        "unavailable_share": share,
        "over_limit": share is not None and share > UNAVAILABLE_SHARE_LIMIT,
        "with_market_reference": with_market,
        "reasons": dict(reasons.most_common()),
        "days": days,
        "freshness": {
            str(league): {
                "complete_until": f.complete_until.isoformat(),
                "file": f.last_update.isoformat() if f.last_update else None,
            }
            for league, f in sorted((context.league_freshness or {}).items())
        },  # fmt: skip
        "overlay": {"counts": summary.get("counts", {}), "issues": summary.get("issues", [])},
    }


def render(report: dict) -> str:
    share = report["unavailable_share"]
    verdict = "aucun match du top 5 sur la période" if share is None else (
        f"{share:.0%} d'indisponibles ({report['matches'] - report['available']} sur {report['matches']}) : "
        + ("au-delà du critère de l'ADR-0011 (un sur cinq)" if report["over_limit"] else "sous le critère (un sur cinq)")
    )  # fmt: skip
    lines = [
        f"# Live du {report['today']} : disponibilité des prochains matchs du top 5",
        "",
        "Produit par `python -m foot_predictor.inference live` (sous-étape 5.14 ; ADR-0011, ADR-0042). Matchs du "
        "périmètre du modèle (championnats du top 5) ; décomptes seulement, les prédictions vont dans `ops.prediction`.",
        "",
        f"- Version des données : `{report['data_version']}` ; modèle : {', '.join(f'`{v}`' for v in report['model_versions'])}.",
        f"- **{verdict}**.",
        f"- Matchs avec une référence de marché avant clôture : {report['with_market_reference']}.",
        f"- Superposition : {report['overlay']['counts'] or 'aucun décompte'} ; "
        f"lignes de football-data inutilisables : {len(report['overlay']['issues'])}.",
        "",
        "| Jour | Matchs du top 5 | Disponibles | Autres statuts | Hors périmètre |",
        "|---|---|---|---|---|",
    ]
    for d in report["days"]:
        others = ", ".join(f"{k} {v}" for k, v in sorted(d["statuses"].items()) if k != AVAILABLE) or "—"
        lines.append(
            f"| {d['day']} | {d['matches']} | {d['statuses'].get(AVAILABLE, 0)} | {others} | {d['out_of_scope']} |"
        )
    lines += ["", "Raisons d'indisponibilité (matchs du top 5) :", ""]
    lines += [f"- {reason} : {n}" for reason, n in report["reasons"].items()] or ["- aucune"]
    lines += ["", "| Championnat (API) | Complet jusqu'au | Fichier de football-data du |", "|---|---|---|"]
    lines += [f"| {k} | {v['complete_until']} | {v['file'] or '—'} |" for k, v in report["freshness"].items()]
    if report["overlay"]["issues"]:
        lines += ["", "Lignes de football-data inutilisables (jamais devinées) :", ""]
        lines += [
            f"- {i['division']} {i['date']} {i['home']} – {i['away']} : {i['reason']}"
            for i in report["overlay"]["issues"]
        ]
    if "saved" in report:
        s = report["saved"]
        lines += ["", f"`ops.prediction` (mode live) : {s['created']} écrite(s), {s['kept']} déjà présente(s), "
                      f"{s['refused']} refusée(s) (après le coup d'envoi)."]  # fmt: skip
    return "\n".join(lines) + "\n"
