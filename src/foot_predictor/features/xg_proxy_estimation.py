"""Estimation unique et contrôle de l'`xg_proxy` (ADR-0032).

    uv run python -m foot_predictor.features.xg_proxy_estimation

1. Estime a et b sur 2015-16 à 2020-21 (jamais au-delà), les écrit dans
   `features/params/xg_proxy.json` (figés).
2. Contrôle la qualité sur 2022-23 à 2024-25 (période de développement) contre l'xG
   d'API-FOOTBALL, là où il existe : corrélation, écart moyen absolu, biais, par championnat du
   top 5, par équipe et par match.
3. Mesure l'effet de la rupture de série des tirs de football-data en Serie A, de 2018-19 à
   2020-21 (ADR-0029) : `xg_proxy` calculé avec les tirs de football-data contre les mêmes
   coefficients appliqués aux tirs d'API-FOOTBALL, et coefficients estimés sans ces saisons.

Rapport : `reports/variables/xg_proxy.md`, chiffres seulement.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.features import xg_proxy
from foot_predictor.features.leagues import LADDERS, TOP5

CONTROL_SEASONS = range(2022, 2025)  # 2022-23 à 2024-25
BREAK = (135, range(2018, 2021))  # Serie A, 2018-19 à 2020-21
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "reports" / "variables" / "xg_proxy.md"
LEAGUE_NAMES = {39: "Premier League", 140: "La Liga", 78: "Bundesliga", 135: "Serie A", 61: "Ligue 1"}


def team_rows(matches: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par (match, équipe) : tirs football-data et API, xG API."""
    base = ["match_id", "season_year", "api_league_id", "status", "excluded"]
    parts = []
    for side in ("home", "away"):
        part = matches[base].copy()
        for column in ("goals_90", "shots_fd", "sot_fd", "shots_api", "sot_api", "xg_api"):
            part[column] = matches[f"{side}_{column}"]
        parts.append(part)
    rows = pd.concat(parts, ignore_index=True)
    return rows[(rows["status"] == "played") & ~rows["excluded"].astype(bool)]


def quality(rows: pd.DataFrame, coef: xg_proxy.XgProxyCoefficients) -> pd.DataFrame:
    rows = rows.assign(proxy=xg_proxy.apply(coef, rows["shots_fd"], rows["sot_fd"]).to_numpy())
    rows = rows.dropna(subset=["proxy", "xg_api"])
    out = []
    for league, group in [*rows.groupby("api_league_id"), ("Total", rows)]:
        proxy, xg = group["proxy"].astype(float), group["xg_api"].astype(float)
        out.append(
            {
                "championnat": LEAGUE_NAMES.get(league, league),
                "lignes": len(group),
                "corrélation": proxy.corr(xg),
                "écart moyen absolu": (proxy - xg).abs().mean(),
                "biais (proxy − xG)": (proxy - xg).mean(),
                "xG moyen": xg.mean(),
            }
        )
    return pd.DataFrame(out)


def break_effect(rows: pd.DataFrame, coef: xg_proxy.XgProxyCoefficients) -> dict:
    league, seasons = BREAK
    part = rows[(rows["api_league_id"] == league) & rows["season_year"].isin(list(seasons))]
    fd = xg_proxy.apply(coef, part["shots_fd"], part["sot_fd"]).astype(float)
    api = xg_proxy.apply(coef, part["shots_api"], part["sot_api"]).astype(float)
    both = fd.notna().to_numpy() & api.notna().to_numpy()
    diff = fd.to_numpy()[both] - api.to_numpy()[both]
    return {"lignes": int(both.sum()), "biais": float(diff.mean()), "écart moyen absolu": float(np.abs(diff).mean())}


def render(coef, without_break, free, table: pd.DataFrame, effect: dict, today: dt.date) -> str:
    lines = [
        f"# xg_proxy : estimation et contrôle — {today.isoformat()}",
        "",
        "Produit par `python -m foot_predictor.features.xg_proxy_estimation` (ADR-0032). Chiffres seulement.",
        "",
        "## Estimation (figée)",
        "",
        f"- `xg_proxy = {coef.on_target:.4f} · tirs cadrés + {coef.off_target:.4f} · tirs non cadrés` "
        f"(moindres carrés sans constante, coefficients positifs ou nuls, tirs de football-data).",
        f"- Estimation libre (sans la contrainte), pour information : {free.on_target:.4f} · cadrés "
        f"{free.off_target:+.4f} · non cadrés. **Non retenue** : un tir ne peut pas retirer de but attendu.",
        "- Saisons 2015-16 à 2020-21, 10 championnats des échelles, "
        f"{coef.n_team_matches} lignes (match, équipe) avec tirs et buts. Aucune saison de validation n'est lue.",
        f"- Sensibilité, sans la Serie A de 2018-19 à 2020-21 (rupture de série, ADR-0029), avec la contrainte : "
        f"{without_break.on_target:.4f} · cadrés + {without_break.off_target:.4f} · non cadrés "
        f"({without_break.n_team_matches} lignes). **Non retenu** : sensibilité seulement.",
        "",
        "## Qualité sur 2022-23 à 2024-25, contre l'xG d'API-FOOTBALL (par équipe et par match)",
        "",
        "| Championnat | Lignes | Corrélation | Écart moyen absolu | Biais (proxy − xG) | xG moyen |",
        "|---|---|---|---|---|---|",
    ]
    for _, row in table.iterrows():
        lines.append(
            f"| {row['championnat']} | {row['lignes']} | {row['corrélation']:.3f} | {row['écart moyen absolu']:.3f} | "
            f"{row['biais (proxy − xG)']:+.3f} | {row['xG moyen']:.3f} |"
        )
    lines += [
        "",
        "L'xG d'API-FOOTBALL couvre environ la moitié des matchs de 2022-23, puis de 99 à 100 % (ADR-0023).",
        "",
        "## Effet de la rupture de série de la Serie A (2018-19 à 2020-21)",
        "",
        f"Mêmes coefficients, appliqués aux tirs de football-data puis aux tirs d'API-FOOTBALL, sur {effect['lignes']} "
        f"lignes communes : biais {effect['biais']:+.3f} xG par équipe et par match, écart moyen absolu "
        f"{effect['écart moyen absolu']:.3f}.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from foot_predictor.features.sources import load_matches

    matches = load_matches(kinds=["league"])
    matches = matches[matches["api_league_id"].isin(list(LADDERS))]
    estimation = matches[matches["season_year"].isin(list(xg_proxy.ESTIMATION_SEASONS))]
    coef = xg_proxy.estimate(estimation)
    league, seasons = BREAK
    without = estimation[~((estimation["api_league_id"] == league) & estimation["season_year"].isin(list(seasons)))]
    coef_without = xg_proxy.estimate(without)
    coef_free = xg_proxy.estimate(estimation, nonnegative=False)
    xg_proxy.save(coef)

    rows = team_rows(matches)
    control = rows[rows["api_league_id"].isin(list(TOP5)) & rows["season_year"].isin(list(CONTROL_SEASONS))]
    table = quality(control, coef)
    effect = break_effect(rows, coef)
    today = dt.datetime.now(dt.UTC).date()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(coef, coef_without, coef_free, table, effect, today), encoding="utf-8")
    print(f"Coefficients : {coef.to_dict()}\nRapport : {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
