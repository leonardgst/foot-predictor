"""Jeu de données versionné : une ligne par (match, équipe), variables G0 à G3 (ADR-0030).

`build_frame(matches, ...)` est une fonction pure : elle reçoit la table des matchs (porte
`features/sources.py`, toutes compétitions) et renvoie le jeu, colonnes dans l'ordre du
registre. `run_build` lit la porte, écrit l'instantané Parquet et son manifeste dans
`data/datasets/<version>/` (ignoré par Git) et trace la version dans
`features.dataset_version`.

Périmètre (décision d.6 de la partie 3) : matchs de **saison régulière** des 10 championnats
des échelles (top 5 et D2), de 2000-01 à 2024-25, terminés, non exclus (ADR-0009), avec un
score au temps réglementaire. Les barrages alimentent l'historique (Elo, glissants, repos),
sans donner de ligne (décision d.10a).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from foot_predictor.features import huis_clos, registry, xg_proxy
from foot_predictor.features.elo import EloParams, compute_elo
from foot_predictor.features.leagues import LADDERS, TOP5
from foot_predictor.features.rest import compute_rest
from foot_predictor.features.rolling import HALF_LIVES, compute_rolling
from foot_predictor.seal import check_seal

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS_ROOT = REPO_ROOT / "data" / "datasets"
ELO_PARAMS_PATH = Path(__file__).resolve().parent / "params" / "elo.json"

FIRST_SEASON = 2000
LAST_SEASON = 2024
LEARNING_FROM = 2015
VALIDATION_FROM = 2021
DATA_FILE = "dataset.parquet"


def load_elo_params(path: Path = ELO_PARAMS_PATH) -> EloParams:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EloParams(**data["params"])


def phase_of(season_year: pd.Series) -> pd.Series:
    """« rodage » avant 2015-16, « apprentissage » de 2015-16 à 2020-21, « validation » ensuite (ADR-0012)."""
    return pd.Series(
        np.select(
            [season_year < LEARNING_FROM, season_year < VALIDATION_FROM],
            ["rodage", "apprentissage"],
            default="validation",
        ),
        index=season_year.index,
    )


def build_frame(
    matches: pd.DataFrame,
    elo_params: EloParams,
    coefficients: xg_proxy.XgProxyCoefficients,
    periods: list[huis_clos.Period] | None = None,
    half_lives: tuple[int, ...] = HALF_LIVES,
) -> pd.DataFrame:
    """Jeu de données à partir de la table des matchs (toutes compétitions), sans accès à la base.

    Refuse une table qui contient un match sous scellés (ADR-0012), comme la porte.
    """
    check_seal(matches["match_date"])
    elo = compute_elo(matches, elo_params)
    rolling = compute_rolling(matches, coefficients, half_lives=half_lives)
    rest = compute_rest(matches)

    rows = matches[
        matches["api_league_id"].isin(list(LADDERS))
        & matches["is_regular_season"]
        & matches["season_year"].between(FIRST_SEASON, LAST_SEASON)
        & (matches["status"] == "played")
        & ~matches["excluded"].astype(bool)
        & matches["home_goals_90"].notna()
        & matches["away_goals_90"].notna()
    ]
    sides = []
    for side, other in (("home", "away"), ("away", "home")):
        sides.append(
            pd.DataFrame(
                {
                    "match_id": rows["match_id"],
                    "team_id": rows[f"{side}_team_id"],
                    "opp_team_id": rows[f"{other}_team_id"],
                    "match_date": rows["match_date"],
                    "match_day": rows["match_day"],
                    "competition_id": rows["competition_id"],
                    "api_league_id": rows["api_league_id"],
                    "season_year": rows["season_year"],
                    "goals_for": rows[f"{side}_goals_90"],
                    "goals_against": rows[f"{other}_goals_90"],
                    "is_home": side == "home",
                }
            )
        )
    frame = pd.concat(sides, ignore_index=True)
    frame["country"] = frame["api_league_id"].map(lambda x: LADDERS[int(x)][0])
    frame["division_level"] = frame["api_league_id"].map(lambda x: LADDERS[int(x)][1]).astype("Int64")
    frame["phase"] = phase_of(frame["season_year"].astype(int))
    frame["eval_population"] = frame["api_league_id"].isin(list(TOP5))
    frame["behind_closed_doors"] = huis_clos.behind_closed_doors(frame["api_league_id"], frame["match_day"], periods)

    keys = ["match_id", "team_id"]
    frame = frame.merge(elo.drop(columns=["is_home"]), on=keys, how="left", validate="one_to_one")
    frame["elo_diff"] = frame["elo_pre"] - frame["opp_elo_pre"]
    frame = frame.merge(rolling.drop(columns=["is_home"]), on=keys, how="left", validate="one_to_one")
    frame = frame.merge(
        rest.drop(columns=["is_home", "rest_reliable"]).merge(rest[["match_id", "team_id", "rest_reliable"]], on=keys),
        on=keys,
        how="left",
        validate="one_to_one",
    )
    # Colonnes de l'adversaire : celles de la ligne de l'adversaire dans le même match.
    own = [c for c in rolling.columns if c not in ("match_id", "team_id", "is_home")]
    own += ["rest_days", "matches_last_14d", "european_match_last_4d"]
    opponent = frame[["match_id", "team_id", *own]].rename(columns={"team_id": "opp_team_id"})
    opponent = opponent.rename(columns={c: f"opp_{c}" for c in own})
    frame = frame.merge(opponent, on=["match_id", "opp_team_id"], how="left", validate="one_to_one")

    expected = registry.columns()
    missing = [c for c in expected if c not in frame.columns]
    if missing:
        raise ValueError(f"Colonnes du registre non calculées : {missing}")
    frame = frame[expected]
    frame = frame.astype(
        {
            "match_id": "int64",
            "team_id": "int64",
            "opp_team_id": "int64",
            "competition_id": "int64",
            "api_league_id": "int64",
            "season_year": "int64",
            "division_level": "int64",
            "goals_for": "int64",
            "goals_against": "int64",
            "elo_matches": "int64",
            "opp_elo_matches": "int64",
            "matches_last_14d": "int64",
            "opp_matches_last_14d": "int64",
            "behind_closed_doors": "int8",
        }
    )
    frame["match_day"] = pd.to_datetime(frame["match_day"]).dt.date
    return frame.sort_values(["match_date", "match_id", "is_home"], ascending=[True, True, False]).reset_index(
        drop=True
    )


# ---------------------------------------------------------------------------------- instantané


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def git_dirty() -> bool | None:
    """Vrai si des fichiers suivis par Git ont des modifications non committées (traçabilité du manifeste)."""
    try:
        done = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(done.stdout.strip())


def counts_of(frame: pd.DataFrame) -> dict:
    by_phase = frame.groupby("phase").size().to_dict()
    by_league = frame.groupby(["api_league_id", "phase"]).size()
    return {
        "rows": int(len(frame)),
        "matches": int(frame["match_id"].nunique()),
        "rows_by_phase": {k: int(v) for k, v in sorted(by_phase.items())},
        "rows_by_league_phase": {f"{league}:{phase}": int(v) for (league, phase), v in sorted(by_league.items())},
        "first_match_day": str(frame["match_day"].min()) if len(frame) else None,
        "last_match_day": str(frame["match_day"].max()) if len(frame) else None,
    }


def manifest_digest(manifest: dict) -> str:
    """sha256 du manifeste, hors champs qui en dépendent (version, empreinte elle-même)."""
    body = {k: v for k, v in manifest.items() if k not in ("version", "manifest_sha256")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def write_snapshot(frame: pd.DataFrame, manifest_base: dict, root: Path, today: dt.date) -> tuple[Path, dict]:
    """Écrit le Parquet et le manifeste dans `root/<version>/`. Version : ds-<date>-<8 car. du sha256>.

    Le Parquet est d'abord écrit dans un dossier temporaire (le nom de version dépend de son
    sha256, via le manifeste), puis le dossier est renommé.
    """
    staging_dir = root / f".en-cours-{today.isoformat()}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    data_path = staging_dir / DATA_FILE
    frame.to_parquet(data_path, index=False, engine="pyarrow", compression="zstd")
    manifest = dict(manifest_base)
    manifest["date"] = today.isoformat()
    manifest["files"] = {DATA_FILE: {"sha256": sha256_file(data_path), "rows": int(len(frame))}}
    digest = manifest_digest(manifest)
    manifest["manifest_sha256"] = digest
    manifest["version"] = f"ds-{today.isoformat()}-{digest[:8]}"
    (staging_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    final_dir = root / manifest["version"]
    if final_dir.exists():
        # Même version = même contenu (le nom vient du sha256) : on garde l'existant.
        for path in staging_dir.iterdir():
            path.unlink()
        staging_dir.rmdir()
    else:
        staging_dir.rename(final_dir)
    return final_dir, manifest
