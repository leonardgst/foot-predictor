"""Commande `features check` : contrôle d'un jeu de données versionné (ADR-0030, rapport I.8).

Rapport versionné `reports/variables/dataset_<version>.md`, chiffres seulement :

- colonnes du jeu contre le registre (mêmes colonnes, même ordre) ;
- aucun match daté à partir du 1er juillet 2025 (scellé) ;
- lignes par phase et par championnat ;
- part de valeurs vides par variable et par championnat, puis par saison ;
- résumé des distributions des variables (période de développement : tout le jeu) ;
- en option (`--invariance`), le contrôle anti-fuite n° 2 sur les données réelles : les lignes
  calculées sur l'historique tronqué à une date de coupe sont identiques à celles calculées sur
  l'historique complet, pour tous les matchs d'avant la coupe.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from foot_predictor.features import huis_clos, registry, xg_proxy
from foot_predictor.features.dataset import build_frame, load_elo_params
from foot_predictor.features.leagues import LADDERS
from foot_predictor.seal import SEAL_TIMESTAMP

LEAGUE_NAMES = {
    39: "PL", 40: "Champ.", 140: "Liga", 141: "Segunda", 78: "BL", 79: "2. BL", 135: "Serie A", 136: "Serie B",
    61: "L1", 62: "L2",
}  # fmt: skip
SEASON_FAMILIES = [
    "elo_pre", "goals_for_ewm_h120", "xgp_for_ewm_h120", "days_since_last_league_match", "rest_days",
]  # fmt: skip
DEFAULT_CUTS = (dt.date(2019, 1, 1), dt.date(2023, 3, 1))


def _pct(value: float) -> str:
    return f"{100 * value:.1f}"


def _table(headers: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
        *("| " + " | ".join(str(c) for c in row) + " |" for row in rows),
    ]


def invariance(cuts=DEFAULT_CUTS, connectable=None) -> list[dict]:
    """Contrôle n° 2 sur les données réelles : historique tronqué à la date de coupe contre historique complet."""
    from foot_predictor.features.sources import load_matches

    params, coef, periods = load_elo_params(), xg_proxy.load(), huis_clos.load_periods()
    full = build_frame(load_matches(connectable), params, coef, periods)
    results = []
    for cut in cuts:
        truncated = build_frame(load_matches(connectable, until=cut), params, coef, periods)
        before = full[full["match_day"] < cut].reset_index(drop=True)
        cut_rows = truncated[truncated["match_day"] < cut].reset_index(drop=True)
        same_shape = before.shape == cut_rows.shape
        identical = same_shape and before.equals(cut_rows)
        differing = []
        if same_shape and not identical:
            for column in before.columns:
                if not before[column].equals(cut_rows[column]):
                    differing.append(column)
        results.append(
            {"cut": cut.isoformat(), "rows": len(before), "identical": identical, "differing_columns": differing}
        )
    return results


def render(frame: pd.DataFrame, manifest: dict, inv: list[dict] | None, today: dt.date) -> str:
    version = manifest["version"]
    expected = registry.columns()
    columns_ok = list(frame.columns) == expected
    sealed = int((pd.to_datetime(frame["match_date"], utc=True) >= SEAL_TIMESTAMP).sum())
    features = [c for c in registry.feature_columns() if not c.startswith("opp_")]
    lines = [
        f"# Contrôle du jeu de données {version} — {today.isoformat()}",
        "",
        "Produit par `python -m foot_predictor.features check` (ADR-0030). Chiffres seulement.",
        "",
        "## 1. Verdicts",
        "",
        f"- Colonnes du jeu contre le registre ({len(expected)} colonnes) : **{'OK' if columns_ok else 'ÉCART'}**.",
        f"- Matchs datés à partir du 1er juillet 2025 : **{sealed}** (attendu : 0).",
        f"- Lignes : {len(frame)} ; matchs : {frame['match_id'].nunique()} ; du {frame['match_day'].min()} au "
        f"{frame['match_day'].max()}.",
        f"- Manifeste : révision `{manifest['alembic_revision']}`, chargement `ops.load_run` n° "
        f"{manifest['load_run_id']}, commit `{(manifest['git_commit'] or '?')[:7]}`, registre "
        f"`{manifest['registry_sha256'][:12]}`, fichier `{manifest['files']['dataset.parquet']['sha256'][:12]}`.",
        f"- Code committé au moment de la construction : "
        f"**{ {False: 'oui', True: 'NON (à reconstruire)', None: 'inconnu'}[manifest.get('git_dirty')] }**.",
    ]
    if inv is not None:
        lines += ["", "## 2. Invariance à la date de coupe (données réelles, contrôle anti-fuite n° 2)", ""]
        lines += _table(
            ["Date de coupe", "Lignes d'avant la coupe", "Identiques", "Colonnes en écart"],
            [[r["cut"], r["rows"], "oui" if r["identical"] else "NON", ", ".join(r["differing_columns"]) or "aucune"]
             for r in inv],
        )  # fmt: skip
    lines += ["", "## 3. Lignes par phase et par championnat", ""]
    counts = frame.groupby(["api_league_id", "phase"]).size().unstack(fill_value=0)
    phases = [p for p in ("rodage", "apprentissage", "validation") if p in counts.columns]
    rows = [[f"{LEAGUE_NAMES[int(league)]} ({league})", *(int(counts.loc[league, p]) for p in phases),
             int(counts.loc[league].sum())] for league in counts.index]  # fmt: skip
    rows.append(["Total", *(int(counts[p].sum()) for p in phases), int(counts.values.sum())])
    lines += _table(["Championnat", *phases, "Total"], rows)

    lines += ["", "## 4. Part de valeurs vides (%) par variable et par championnat", ""]
    lines += ["Colonnes de l'équipe ; celles de l'adversaire (`opp_`) sont symétriques.", ""]
    leagues = sorted(frame["api_league_id"].unique(), key=lambda x: list(LADDERS).index(int(x)))
    rows = []
    for column in features:
        by_league = frame.groupby("api_league_id")[column].apply(lambda s: s.isna().mean())
        rows.append([column, *(_pct(by_league[league]) for league in leagues), _pct(frame[column].isna().mean())])
    lines += _table(["Variable", *(LEAGUE_NAMES[int(league)] for league in leagues), "Tout"], rows)

    lines += ["", "## 5. Part de valeurs vides (%) par saison, variables représentatives", ""]
    by_season = frame.groupby("season_year")
    rows = [[season, *(_pct(group[c].isna().mean()) for c in SEASON_FAMILIES), _pct(group["rest_reliable"].mean())]
            for season, group in by_season]  # fmt: skip
    lines += _table(["Saison", *SEASON_FAMILIES, "rest_reliable (% vrai)"], rows)

    lines += ["", "## 6. Distributions (toutes les lignes, période de développement)", ""]
    rows = []
    for column in features:
        values = pd.to_numeric(frame[column], errors="coerce").astype(float)
        q = values.quantile([0.0, 0.25, 0.5, 0.75, 1.0]).to_numpy()
        rows.append(
            [column, int(values.notna().sum()), f"{values.mean():.3f}", f"{values.std():.3f}",
             *(f"{v:.3f}" for v in q)]
        )  # fmt: skip
    lines += _table(["Variable", "Non vides", "Moyenne", "Écart type", "Min", "Q1", "Médiane", "Q3", "Max"], rows)
    lines.append("")
    return "\n".join(lines)


def run_check(
    version: str | None = None,
    output_root: Path | None = None,
    report_dir: Path = Path("reports") / "variables",
    with_invariance: bool = False,
    today: dt.date | None = None,
) -> Path:
    from foot_predictor.features.sources import load_dataset

    frame, manifest = load_dataset(version, output_root)
    inv = invariance() if with_invariance else None
    today = today or dt.datetime.now(dt.UTC).date()
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"dataset_{manifest['version']}.md"
    path.write_text(render(frame, manifest, inv, today), encoding="utf-8")
    if inv is not None and not all(r["identical"] for r in inv):
        raise SystemExit(f"Invariance à la date de coupe en échec : voir {path}")
    return path
