"""Estimation unique et contrôle de l'`xg_proxy` (ADR-0032, source des tirs : ADR-0035).

    uv run python -m foot_predictor.features.xg_proxy_estimation

1. Estime a et b sur 2015-16 à 2020-21 (jamais au-delà), avec les tirs **retenus**
   (`xg_proxy.select_shots` : API-FOOTBALL depuis 2015-16 quand elle a les quatre valeurs,
   sinon football-data), et les écrit dans `features/params/xg_proxy.json` (figés).
   Pour comparaison seulement : l'estimation libre (sans contrainte de positivité) et
   l'ancienne règle (tirs de football-data seuls, ADR-0029).
2. Contrôle la qualité sur 2022-23 à 2024-25 (période de développement) contre l'xG
   d'API-FOOTBALL, là où il existe, par championnat du top 5, par équipe et par match : avec
   les tirs retenus, puis avec les seuls tirs de football-data (situation des matchs joués
   après le gel, ADR-0011).
3. Mesure l'accord des deux sources sur les matchs communs du top 5 (2015-16 à 2024-25) : part
   de matchs identiques, et écart d'`xg_proxy` entre football-data et API, par championnat. C'est
   le risque du changement de source après le gel (ADR-0035).

Rapport : `reports/variables/xg_proxy.md`, chiffres seulement (période de développement).
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
AGREEMENT_SEASONS = range(2015, 2025)  # 2015-16 à 2024-25
BREAK = (135, range(2018, 2021))  # Serie A, 2018-19 à 2020-21
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "reports" / "variables" / "xg_proxy.md"
LEAGUE_NAMES = {39: "Premier League", 140: "La Liga", 78: "Bundesliga", 135: "Serie A", 61: "Ligue 1"}
_API = ("home_shots_api", "home_sot_api", "away_shots_api", "away_sot_api")
_FD = ("home_shots_fd", "home_sot_fd", "away_shots_fd", "away_sot_fd")


def team_rows(matches: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par (match, équipe) : tirs retenus, tirs football-data et API, xG API."""
    base = ["match_id", "season_year", "api_league_id", "status", "excluded"]
    selected = xg_proxy.select_shots(matches)
    parts = []
    for side in ("home", "away"):
        part = matches[base].copy()
        for column in ("goals_90", "shots_fd", "sot_fd", "shots_api", "sot_api", "xg_api"):
            part[column] = matches[f"{side}_{column}"]
        part["shots_sel"] = selected[f"{side}_shots"]
        part["sot_sel"] = selected[f"{side}_sot"]
        part["shots_source"] = selected["shots_source"]
        parts.append(part)
    rows = pd.concat(parts, ignore_index=True)
    return rows[(rows["status"] == "played") & ~rows["excluded"].astype(bool)]


def quality(rows: pd.DataFrame, coef: xg_proxy.XgProxyCoefficients, shots: str = "sel") -> pd.DataFrame:
    """Qualité de l'`xg_proxy` contre l'xG API ; `shots` : `sel` (tirs retenus) ou `fd` (football-data seuls)."""
    rows = rows.assign(proxy=xg_proxy.apply(coef, rows[f"shots_{shots}"], rows[f"sot_{shots}"]).to_numpy())
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


def source_agreement(matches: pd.DataFrame, coef: xg_proxy.XgProxyCoefficients) -> pd.DataFrame:
    """Matchs communs du top 5 (les deux sources complètes) : part identique, écart d'`xg_proxy` fd − API."""
    part = matches[
        matches["api_league_id"].isin(list(TOP5))
        & matches["season_year"].isin(list(AGREEMENT_SEASONS))
        & (matches["status"] == "played")
        & ~matches["excluded"].astype(bool)
    ]
    part = part[part[list(_API + _FD)].notna().all(axis=1)]
    out = []
    for league, group in [*part.groupby("api_league_id"), ("Total", part)]:
        same = np.ones(len(group), dtype=bool)
        for api, fd in zip(_API, _FD, strict=True):
            same &= (group[api] == group[fd]).to_numpy(dtype=bool)
        diffs = []
        for side in ("home", "away"):
            fd_value = xg_proxy.apply(coef, group[f"{side}_shots_fd"], group[f"{side}_sot_fd"]).astype(float)
            api_value = xg_proxy.apply(coef, group[f"{side}_shots_api"], group[f"{side}_sot_api"]).astype(float)
            diffs.append(fd_value.to_numpy() - api_value.to_numpy())
        diff = np.concatenate(diffs)
        out.append(
            {
                "championnat": LEAGUE_NAMES.get(league, league),
                "matchs": len(group),
                "identiques": float(same.mean()) if len(group) else np.nan,
                "biais": float(np.nanmean(diff)),
                "écart moyen absolu": float(np.nanmean(np.abs(diff))),
            }
        )
    return pd.DataFrame(out)


def source_shares(matches: pd.DataFrame) -> pd.DataFrame:
    """Part des matchs de championnat par source retenue, par période et par niveau (estimation et validation)."""
    part = matches[(matches["status"] == "played") & ~matches["excluded"].astype(bool)]
    part = part[part["season_year"].between(2015, 2024)]
    source = xg_proxy.select_shots(part)["shots_source"].fillna("aucune")
    frame = pd.DataFrame(
        {
            "période": np.where(part["season_year"] <= 2020, "2015-16 à 2020-21", "2021-22 à 2024-25"),
            "niveau": np.where(part["api_league_id"].isin(list(TOP5)), "top 5", "D2"),
            "source": source.to_numpy(),
        }
    )
    table = frame.groupby(["période", "niveau"])["source"].value_counts(normalize=True).unstack(fill_value=0.0)
    return table.reindex(columns=["api", "football_data", "aucune"], fill_value=0.0)


def break_effect(rows: pd.DataFrame, coef: xg_proxy.XgProxyCoefficients) -> dict:
    """Serie A 2018-19 à 2020-21 : `xg_proxy` des tirs de football-data (ancienne règle) contre celui des tirs retenus."""
    league, seasons = BREAK
    part = rows[(rows["api_league_id"] == league) & rows["season_year"].isin(list(seasons))]
    fd = xg_proxy.apply(coef, part["shots_fd"], part["sot_fd"]).astype(float)
    sel = xg_proxy.apply(coef, part["shots_sel"], part["sot_sel"]).astype(float)
    both = fd.notna().to_numpy() & sel.notna().to_numpy()
    diff = fd.to_numpy()[both] - sel.to_numpy()[both]
    return {"lignes": int(both.sum()), "biais": float(diff.mean()), "écart moyen absolu": float(np.abs(diff).mean())}


def _quality_lines(table: pd.DataFrame) -> list[str]:
    lines = [
        "| Championnat | Lignes | Corrélation | Écart moyen absolu | Biais (proxy − xG) | xG moyen |",
        "|---|---|---|---|---|---|",
    ]
    for _, row in table.iterrows():
        lines.append(
            f"| {row['championnat']} | {row['lignes']} | {row['corrélation']:.3f} | {row['écart moyen absolu']:.3f} | "
            f"{row['biais (proxy − xG)']:+.3f} | {row['xG moyen']:.3f} |"
        )
    return lines


def render(
    coef, free, fd_only, table_sel, table_fd, agreement, shares, effect: dict, today: dt.date
) -> str:  # fmt: skip
    lines = [
        f"# xg_proxy : estimation et contrôle — {today.isoformat()}",
        "",
        "Produit par `python -m foot_predictor.features.xg_proxy_estimation` (ADR-0032 ; source des tirs : ADR-0035). "
        "Chiffres seulement, période de développement.",
        "",
        "## Estimation (figée)",
        "",
        f"- `xg_proxy = {coef.on_target:.4f} · tirs cadrés + {coef.off_target:.4f} · tirs non cadrés` "
        "(moindres carrés sans constante, coefficients positifs ou nuls).",
        "- **Tirs retenus** (ADR-0035) : API-FOOTBALL pour un match joué depuis 2015-16 où elle a les tirs et les tirs "
        "cadrés des deux équipes ; sinon football-data. Choix par match.",
        f"- Estimation libre (sans la contrainte), pour information : {free.on_target:.4f} · cadrés "
        f"{free.off_target:+.4f} · non cadrés. **Non retenue** : un tir ne peut pas retirer de but attendu.",
        f"- Ancienne règle (tirs de football-data seuls, ADR-0029), avec la contrainte : {fd_only.on_target:.4f} · "
        f"cadrés + {fd_only.off_target:.4f} · non cadrés ({fd_only.n_team_matches} lignes). **Remplacée.**",
        "- Saisons 2015-16 à 2020-21, 10 championnats des échelles, "
        f"{coef.n_team_matches} lignes (match, équipe) avec tirs et buts. Aucune saison de validation n'est lue.",
        "",
        "## Source retenue, part des matchs de championnat",
        "",
        "| Période | Niveau | API | football-data | aucune |",
        "|---|---|---|---|---|",
    ]
    for (period, level), row in shares.iterrows():
        lines.append(f"| {period} | {level} | {row['api']:.1%} | {row['football_data']:.1%} | {row['aucune']:.1%} |")
    lines += [
        "",
        "## Qualité sur 2022-23 à 2024-25, contre l'xG d'API-FOOTBALL (par équipe et par match)",
        "",
        "Avec les tirs retenus (ceux de l'API sur cette période) :",
        "",
        *_quality_lines(table_sel),
        "",
        "Avec les seuls tirs de football-data, **situation des matchs joués après le gel** (ADR-0011) :",
        "",
        *_quality_lines(table_fd),
        "",
        "L'xG d'API-FOOTBALL couvre environ la moitié des matchs de 2022-23, puis de 99 à 100 % (ADR-0023).",
        "",
        "## Accord des deux sources, matchs communs du top 5 (2015-16 à 2024-25)",
        "",
        "Part de matchs aux quatre valeurs identiques, et écart d'`xg_proxy` (football-data − API, par équipe et par "
        "match) avec les coefficients figés. Après le gel, seuls les tirs de football-data existent : c'est l'écart "
        "que subiront les glissants.",
        "",
        "| Championnat | Matchs | Identiques | Biais (fd − API) | Écart moyen absolu |",
        "|---|---|---|---|---|",
    ]
    for _, row in agreement.iterrows():
        lines.append(
            f"| {row['championnat']} | {row['matchs']} | {row['identiques']:.1%} | {row['biais']:+.3f} | "
            f"{row['écart moyen absolu']:.3f} |"
        )
    lines += [
        "",
        "## Rupture de série de la Serie A (2018-19 à 2020-21), corrigée",
        "",
        f"Mêmes coefficients, tirs de football-data (ancienne règle) contre tirs retenus (API), sur {effect['lignes']} "
        f"lignes : biais {effect['biais']:+.3f} xG par équipe et par match, écart moyen absolu "
        f"{effect['écart moyen absolu']:.3f}. Avec la nouvelle règle, ces trois saisons lisent les tirs de l'API.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from foot_predictor.features.sources import load_matches

    matches = load_matches(kinds=["league"])
    matches = matches[matches["api_league_id"].isin(list(LADDERS))]
    estimation = matches[matches["season_year"].isin(list(xg_proxy.ESTIMATION_SEASONS))]
    coef = xg_proxy.estimate(estimation)
    coef_free = xg_proxy.estimate(estimation, nonnegative=False)
    coef_fd_only = xg_proxy.estimate(estimation.drop(columns=list(_API)))  # sans colonnes API : football-data seul
    xg_proxy.save(coef)

    rows = team_rows(matches)
    control = rows[rows["api_league_id"].isin(list(TOP5)) & rows["season_year"].isin(list(CONTROL_SEASONS))]
    today = dt.datetime.now(dt.UTC).date()
    report = render(
        coef,
        coef_free,
        coef_fd_only,
        quality(control, coef, "sel"),
        quality(control, coef, "fd"),
        source_agreement(matches, coef),
        source_shares(matches),
        break_effect(rows, coef),
        today,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Coefficients : {coef.to_dict()}\nRapport : {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
