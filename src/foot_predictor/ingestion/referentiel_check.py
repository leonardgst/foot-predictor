"""Contrôle J3 du référentiel : `reports/data_quality/referentiel_<AAAA-MM-JJ>.md` (ADR-0008, ADR-0020).

Lit `staging` et la dernière ligne réussie de `ops.load_run` (les décomptes
qui ne se déduisent pas des tables : appariement football-data, entrées
exclues avant d'être anonymes). Le rapport est **versionné** : il ne contient
que des nombres, des libellés de compétitions et, pour les matchs football-data
non appariés d'avant le scellé, des libellés d'équipes et des dates. Aucun nom
ni identifiant de joueur, aucun score (ADR-0012).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from foot_predictor.seal import SEAL_DATE

MATCH_RATE_TARGET = 99.5  # ADR-0008, critère de révision de la règle 2
TOP5 = (39, 140, 78, 135, 61)


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.2f} %" if whole else "n. c."


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def _by_league(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: dict[tuple[int, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["league"], row["name"]), []).append(row)
    return [(name, group) for (_, name), group in sorted(groups.items())]


def collect(connection) -> dict:
    """Toutes les mesures du rapport, en nombres."""
    q = lambda sql, **params: connection.execute(text(sql), params)  # noqa: E731
    run = (
        q(
            "SELECT id, started_at, git_commit, duration_seconds, counts, fingerprints FROM ops.load_run "
            "WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
        )
        .mappings()
        .first()
    )
    data: dict = {"run": dict(run) if run else None}
    data["volumes"] = dict(q(
        "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'staging' ORDER BY relname"
    ).all())  # fmt: skip
    data["volumes"] = {t: q(f"SELECT count(*) FROM staging.{t}").scalar_one() for t in data["volumes"]}
    data["players"] = (
        q(
            "SELECT count(*) AS total, count(DISTINCT api_player_id) AS distinct_api, "
            "count(*) FILTER (WHERE api_player_id IS NULL) AS without_api FROM staging.player"
        )
        .mappings()
        .one()
    )
    data["lineup_duplicates"] = q(
        "SELECT count(*) FROM (SELECT match_id, player_id FROM staging.lineup GROUP BY 1, 2 HAVING count(*) > 1) d"
    ).scalar_one()
    data["lineup_players_in_two_teams"] = q(
        "SELECT count(*) FROM (SELECT match_id, player_id FROM staging.lineup GROUP BY 1, 2 "
        "HAVING count(DISTINCT team_id) > 1) d"
    ).scalar_one()
    per_competition = """
        SELECT c.api_league_id AS league, c.name, c.kind, s.year,
               count(DISTINCT m.id) AS matches,
               count(DISTINCT m.id) FILTER (WHERE m.origin = 'hors_api') AS hors_api,
               count(DISTINCT m.id) FILTER (WHERE m.status = 'played' AND m.origin = 'api') AS played_api,
               count(DISTINCT m.id) FILTER (WHERE m.status = 'played' AND m.origin = 'api'
                   AND NOT EXISTS (SELECT 1 FROM staging.lineup l WHERE l.match_id = m.id)) AS played_without_lineup,
               count(DISTINCT m.id) FILTER (WHERE tm.collision_excluded > 0) AS matches_with_excluded,
               coalesce(sum(tm.collision_excluded), 0) AS excluded_entries,
               coalesce(sum(tm.unknown_starters), 0) AS unknown_starters,
               count(DISTINCT m.id) FILTER (WHERE m.excluded) AS excluded_matches
        FROM staging.match m
        JOIN staging.competition c ON c.id = m.competition_id
        JOIN staging.season s ON s.id = m.season_id
        LEFT JOIN staging.team_match tm ON tm.match_id = m.id
        GROUP BY 1, 2, 3, 4 ORDER BY 1, 4
    """
    data["per_competition_season"] = [dict(r) for r in q(per_competition).mappings()]
    data["exclusions"] = dict(q(
        "SELECT exclusion_reason, count(*) FROM staging.match WHERE excluded GROUP BY 1 ORDER BY 1"
    ).all())  # fmt: skip
    data["teams_by_origin"] = dict(q("SELECT origin, count(*) FROM staging.team GROUP BY 1 ORDER BY 1").all())
    data["shots"] = collect_shots(connection)
    data["odds"] = collect_odds(connection)
    return data


# Tirs par match (les deux équipes) selon football-data (fd) et API-FOOTBALL (api), matchs
# de championnat terminés et non exclus, **avant le scellé seulement** (ADR-0012, ADR-0028) :
# une valeur de tir est une valeur de match, elle ne se lit pas après le 30 juin 2025.
SHOTS_SQL = """
WITH per_team AS (
    SELECT m.id AS match_id, c.api_league_id AS league, c.name, s.year,
           e.shots AS fd_shots, e.shots_on_target AS fd_sot,
           a.shots_total AS api_shots, a.shots_on_goal AS api_sot
    FROM staging.match m
    JOIN staging.competition c ON c.id = m.competition_id AND c.kind = 'league'
    JOIN staging.season s ON s.id = m.season_id
    JOIN staging.team_match tm ON tm.match_id = m.id
    LEFT JOIN staging.team_match_stats_external e ON e.team_match_id = tm.id AND e.source = 'football_data'
    LEFT JOIN staging.team_match_stats a ON a.team_match_id = tm.id
    WHERE m.match_date < :seal AND m.status = 'played' AND NOT m.excluded
      AND EXISTS (SELECT 1 FROM staging.match_source_mapping msm WHERE msm.match_id = m.id)
), per_match AS (
    SELECT match_id, league, name, year,
           bool_and(fd_shots IS NOT NULL AND fd_sot IS NOT NULL) AS fd_ok,
           bool_and(api_shots IS NOT NULL AND api_sot IS NOT NULL) AS api_ok,
           bool_and(fd_shots = api_shots AND fd_sot = api_sot) AS same,
           sum(abs(fd_shots - api_shots)) AS d_shots, sum(abs(fd_sot - api_sot)) AS d_sot
    FROM per_team GROUP BY 1, 2, 3, 4
)
SELECT league, name, year, count(*) AS matches,
       count(*) FILTER (WHERE fd_ok) AS fd_matches,
       count(*) FILTER (WHERE api_ok) AS api_matches,
       count(*) FILTER (WHERE fd_ok AND api_ok) AS common,
       count(*) FILTER (WHERE fd_ok AND api_ok AND same) AS identical,
       coalesce(sum(d_shots) FILTER (WHERE fd_ok AND api_ok), 0) AS abs_diff_shots,
       coalesce(sum(d_sot) FILTER (WHERE fd_ok AND api_ok), 0) AS abs_diff_sot
FROM per_match GROUP BY 1, 2, 3 ORDER BY 1, 3
"""


def collect_shots(connection) -> list[dict]:
    """Présence des tirs par source et recouvrement sur les matchs communs, par championnat-saison."""
    connection.execute(text("SET max_parallel_workers_per_gather = 0"))  # /dev/shm du conteneur (E-035)
    return [dict(r) for r in connection.execute(text(SHOTS_SQL), {"seal": SEAL_DATE}).mappings()]


def render_shots(rows: list[dict]) -> list[str]:
    """Section « tirs » : couverture football-data et API, recouvrement sur les matchs communs (ADR-0029)."""
    lines = [
        "",
        "## 6. Tirs de football-data et d'API-FOOTBALL (ADR-0029)",
        "",
        f"Matchs de championnat terminés, non exclus, rattachés à football-data, **avant le "
        f"{SEAL_DATE:%d/%m/%Y}** (scellé, ADR-0012). « Complet » : tirs et tirs cadrés des deux équipes. "
        "Écart moyen absolu : par équipe et par match, sur les matchs communs.",
        "",
    ]
    if not rows:
        return lines + ["- Aucun tir chargé."]
    keys = ("matches", "fd_matches", "api_matches", "common", "identical", "abs_diff_shots", "abs_diff_sot")
    by_league: dict[tuple, dict] = {}
    for r in rows:
        agg = by_league.setdefault((r["league"], r["name"]), dict.fromkeys(keys, 0))
        for key in keys:
            agg[key] += r[key]
    total = {key: sum(a[key] for a in by_league.values()) for key in keys}

    def row(label: str, a: dict) -> list:
        teams = 2 * a["common"]
        return [
            label,
            a["matches"],
            _pct(a["fd_matches"], a["matches"]),
            _pct(a["api_matches"], a["matches"]),
            a["common"],
            _pct(a["identical"], a["common"]),
            f"{a['abs_diff_shots'] / teams:.2f}" if teams else "-",
            f"{a['abs_diff_sot'] / teams:.2f}" if teams else "-",
        ]

    headers = [
        "Championnat",
        "Matchs",
        "football-data complet",
        "API complet",
        "Communs",
        "Identiques",
        "Écart tirs",
        "Écart cadrés",
    ]
    lines += _table(headers, [row(f"{name} ({league})", a) for (league, name), a in sorted(by_league.items())])
    lines += ["", *_table(headers, [row("Total", total)])]
    first: dict[tuple, int] = {}
    for r in rows:
        if r["fd_matches"] and (r["league"], r["name"]) not in first:
            first[(r["league"], r["name"])] = r["year"]
    lines += [
        "",
        "Première saison avec des tirs football-data : "
        + ", ".join(f"{name} {year}-{(year + 1) % 100:02d}" for (_, name), year in sorted(first.items()))
        + ".",
    ]
    return lines


# Présence des cotes plus/moins 2,5 (ADR-0036), matchs de championnat du top 5 terminés et non
# exclus, par saison. **Décomptes de présence seulement**, avant comme après le scellé : aucune
# valeur de cote n'est lue (ADR-0012, ADR-0028).
ODDS_SQL = """
SELECT c.api_league_id AS league, c.name, s.year, (m.match_date >= :seal) AS sealed,
       count(*) AS matches,
       count(pre.id) AS pre_matches,
       count(clo.id) AS close_matches,
       count(*) FILTER (WHERE pre.odds_column = 'Avg') AS pre_avg,
       count(*) FILTER (WHERE pre.odds_column = 'BbAv') AS pre_bbav,
       count(*) FILTER (WHERE pre.odds_column NOT IN ('Avg', 'BbAv')) AS pre_bookmaker
FROM staging.match m
JOIN staging.competition c ON c.id = m.competition_id AND c.kind = 'league'
JOIN staging.season s ON s.id = m.season_id
LEFT JOIN staging.match_odds pre ON pre.match_id = m.id AND pre.source = 'football_data' AND pre.version = 'avant_cloture'
LEFT JOIN staging.match_odds clo ON clo.match_id = m.id AND clo.source = 'football_data' AND clo.version = 'cloture'
WHERE c.api_league_id IN :top5 AND m.status = 'played' AND NOT m.excluded
GROUP BY 1, 2, 3, 4 ORDER BY 1, 3, 4
"""


def collect_odds(connection) -> list[dict]:
    """Présence des cotes par championnat du top 5, saison et côté du scellé (décomptes seulement)."""
    from sqlalchemy import bindparam

    connection.execute(text("SET max_parallel_workers_per_gather = 0"))  # /dev/shm du conteneur (E-035)
    query = text(ODDS_SQL).bindparams(bindparam("top5", expanding=True))
    return [dict(r) for r in connection.execute(query, {"seal": SEAL_DATE, "top5": list(TOP5)}).mappings()]


def render_odds(rows: list[dict]) -> list[str]:
    """Section « cotes » : présence des cotes plus/moins 2,5 par championnat et par saison (ADR-0036)."""
    lines = [
        "",
        "## 7. Cotes plus/moins 2,5 de football-data (ADR-0036)",
        "",
        "Matchs de championnat du top 5 terminés et non exclus. Part des matchs avec une cote « avant clôture » "
        "(et, parmi eux, colonne retenue : moyenne de marché `Avg`, agrégat BetBrain `BbAv`, un bookmaker) et "
        f"avec une cote de clôture. Après le {SEAL_DATE:%d/%m/%Y} : **présence seulement** (scellé, ADR-0012).",
        "",
    ]
    if not rows:
        return lines + ["- Aucune cote chargée."]
    headers = ["Championnat", "Saison", "Matchs", "Avant clôture", "dont Avg", "dont BbAv", "dont un bookmaker",
               "Clôture"]  # fmt: skip
    table = []
    for r in rows:
        season = f"{r['year']}-{(r['year'] + 1) % 100:02d}" + (" (scellé)" if r["sealed"] else "")
        table.append(
            [f"{r['name']} ({r['league']})", season, r["matches"], _pct(r["pre_matches"], r["matches"]),
             r["pre_avg"], r["pre_bbav"], r["pre_bookmaker"], _pct(r["close_matches"], r["matches"])]
        )  # fmt: skip
    lines += _table(headers, table)
    dev = [r for r in rows if not r["sealed"] and 2015 <= r["year"] <= 2024]
    matches = sum(r["matches"] for r in dev)
    lines += [
        "",
        f"Période d'apprentissage et de validation (2015-16 à 2024-25) : {matches} matchs ; avant clôture "
        f"{_pct(sum(r['pre_matches'] for r in dev), matches)}, clôture {_pct(sum(r['close_matches'] for r in dev), matches)}. "
        "Aucune cote de clôture avant 2019-20 dans les fichiers.",
    ]
    return lines


def render(data: dict, today: dt.date) -> str:
    run = data["run"]
    counts = (run or {}).get("counts") or {}
    lines = [
        f"# Contrôle du référentiel (J3) — {today.isoformat()}",
        "",
        "Produit par `python -m foot_predictor.ingestion check-referentiel`. Chiffres seulement : aucun nom ni "
        "identifiant de joueur, aucun score (ADR-0012). Décisions : ADR-0008, ADR-0009, ADR-0020, ADR-0023.",
        "",
        "## 1. Dernier chargement",
        "",
    ]
    if run:
        lines += [
            f"- `ops.load_run` n° {run['id']}, {run['started_at']:%Y-%m-%d %H:%M} UTC, commit "
            f"`{(run['git_commit'] or '?')[:7]}`, durée {run['duration_seconds']} s.",
        ]
    else:
        lines += ["- Aucun chargement réussi dans `ops.load_run`."]
    lines += ["", *_table(["Table", "Lignes"], [[t, f"{n:,}".replace(",", " ")] for t, n in data["volumes"].items()])]

    p = data["players"]
    ok = p["total"] == p["distinct_api"] and not p["without_api"] and not data["lineup_duplicates"]
    lines += [
        "",
        "## 2. Identité des joueurs (ADR-0008, règle 1)",
        "",
        f"- Verdict : **{'OK' if ok else 'À REGARDER'}** — chaque joueur de composition correspond à une seule "
        "entité interne, créée depuis un identifiant API.",
        f"- Joueurs : {p['total']} ; identifiants API distincts : {p['distinct_api']} ; sans identifiant API : "
        f"{p['without_api']}.",
        f"- (match, joueur) en double dans les compositions : {data['lineup_duplicates']} ; joueur chez deux "
        f"équipes dans un même match : {data['lineup_players_in_two_teams']}.",
        f"- Entrées sans identifiant (0 ou absent), non créées : {counts.get('lineup_unknown_entries', '?')} "
        f"(compositions), {counts.get('stats_unknown_entries', '?')} (statistiques).",
    ]

    lines += ["", "## 3. Appariement football-data (ADR-0008, règle 2)", ""]
    rates = counts.get("fd_rates") or {}
    if rates:
        by_div: dict[str, list[int]] = {}
        for key, (matched, total) in rates.items():
            division = key.split(":")[0]
            by_div.setdefault(division, [0, 0])
            by_div[division][0] += matched
            by_div[division][1] += total
        matched, total = sum(v[0] for v in by_div.values()), sum(v[1] for v in by_div.values())
        verdict = "OK" if total and 100 * matched / total >= MATCH_RATE_TARGET else "SOUS LE SEUIL"
        lines += [
            f"- Période couverte par l'API : **{matched} / {total} lignes appariées ({_pct(matched, total)})** ; "
            f"seuil {MATCH_RATE_TARGET} % : **{verdict}**.",
            f"- Hors couverture API : {counts.get('fd_matches_hors_api', 0)} matchs créés par football-data ; "
            f"{data['teams_by_origin'].get('hors_api', 0)} équipes « hors_api ».",
            f"- Écarts de score entre sources (avant le 1er juillet 2025 seulement) : "
            f"{counts.get('fd_scores_different', 0)} sur {counts.get('fd_scores_compared', 0)} comparés.",
            "",
            *_table(
                ["Division", "Appariées", "Lignes", "Taux"],
                [[d, v[0], v[1], _pct(v[0], v[1])] for d, v in sorted(by_div.items())],
            ),  # fmt: skip
        ]
        below = [(k, v) for k, v in rates.items() if v[0] < v[1]]
        if below:
            lines += ["", "Saisons sous 100 % :", ""]
            lines += _table(["Division:saison", "Appariées", "Lignes"], [[k, v[0], v[1]] for k, v in below])
        unmatched = counts.get("fd_unmatched_before_seal") or []
        lines += [
            "",
            f"Matchs football-data non appariés : {len(unmatched)} avant le scellé (listés), "
            f"{counts.get('fd_unmatched_after_seal', 0)} après (décompte seul).",
        ]
        if unmatched:
            lines += ["", *_table(["Division", "Saison", "Date", "Domicile", "Extérieur", "Raison"], unmatched)]
    else:
        lines += ["- Pas de brut football-data dans le dernier chargement."]

    rows = data["per_competition_season"]
    top5 = [r for r in rows if r["league"] in TOP5 and r["kind"] == "league"]
    lines += [
        "",
        "## 4. Collisions : entrées exclues (ADR-0020)",
        "",
        f"- Entrées exclues : {counts.get('lineup_entries_excluded', '?')} dans les compositions, "
        f"{counts.get('stats_entries_excluded', '?')} dans les statistiques ; résolues par le numéro de la "
        f"composition (2b) : {counts.get('collision_entries_resolved_2b', '?')}.",
        f"- Identifiants en collision « même jour » : {counts.get('collision_ids_same_day', '?')} ; « deux "
        f"naissances » : {counts.get('collision_ids_birth', '?')}.",
        "- **Critères de révision** :",
        f"  - matchs de championnat du top 5 avec au moins une entrée de composition exclue : "
        f"{counts.get('top5_matches_with_excluded_entry', '?')} sur {counts.get('top5_matches_detailed', '?')} "
        f"({_pct(counts.get('top5_matches_with_excluded_entry', 0), counts.get('top5_matches_detailed', 0))} ; "
        "seuil : 1 %) ;",
        f"  - joueur-saisons du top 5 (au moins 10 titularisations) qui perdent plus de 10 % de leurs "
        f"titularisations : {counts.get('top5_player_seasons_over_10pct', '?')} (au plus "
        f"{counts.get('top5_max_share_excluded_pct', '?')} %) ; à réexaminer au J9 (ADR-0020).",
        "",
        "Championnats du top 5 : saisons avec au moins une entrée exclue ou un titulaire inconnu, puis total par "
        "championnat (toutes saisons).",
        "",
        *_table(
            ["Championnat", "Saison", "Matchs", "Matchs avec exclusion", "Entrées exclues", "Titulaires inconnus"],
            [
                [
                    r["name"],
                    r["year"],
                    r["matches"],
                    r["matches_with_excluded"],
                    r["excluded_entries"],
                    r["unknown_starters"],
                ]
                for r in top5
                if r["matches_with_excluded"] or r["unknown_starters"]
            ]
            + [
                [
                    f"**{name}**",
                    "total",
                    sum(r["matches"] for r in group),
                    sum(r["matches_with_excluded"] for r in group),
                    sum(r["excluded_entries"] for r in group),
                    sum(r["unknown_starters"] for r in group),
                ]
                for name, group in _by_league(top5)
            ],
        ),  # fmt: skip
    ]

    by_comp: dict[tuple, dict] = {}
    for r in rows:
        agg = by_comp.setdefault((r["league"], r["name"], r["kind"]), {k: 0 for k in (
            "matches", "hors_api", "played_api", "played_without_lineup", "excluded_entries", "unknown_starters",
            "excluded_matches")})  # fmt: skip
        for key in agg:
            agg[key] += r[key]
    lines += [
        "",
        "## 5. Par compétition : titulaires inconnus, matchs sans composition, exclusions (ADR-0009)",
        "",
        "Matchs terminés sans composition : attendu dans les coupes (seuls les matchs d'une équipe suivie ont un "
        "détail) et dans les saisons anciennes sans compositions.",
        "",
        *_table(
            [
                "Compétition (league.id)",
                "Type",
                "Matchs",
                "dont hors API",
                "Terminés (API)",
                "Terminés sans composition",
                "Titulaires inconnus",
                "Entrées exclues",
                "Matchs exclus (ADR-0009)",
            ],
            [
                [
                    f"{name} ({league})",
                    kind,
                    a["matches"],
                    a["hors_api"],
                    a["played_api"],
                    a["played_without_lineup"],
                    a["unknown_starters"],
                    a["excluded_entries"],
                    a["excluded_matches"],
                ]
                for (league, name, kind), a in sorted(by_comp.items(), key=lambda item: item[0][0])
            ],
        ),  # fmt: skip
        "",
        "Matchs exclus par motif : "
        + (", ".join(f"{reason} {n}" for reason, n in data["exclusions"].items()) or "aucun")
        + ".",
        "",
    ]
    lines += render_shots(data.get("shots") or [])
    lines += render_odds(data.get("odds") or [])
    lines.append("")
    return "\n".join(lines)


def run_check(engine: Engine, output_dir: Path, today: dt.date | None = None) -> Path:
    today = today or dt.datetime.now(dt.UTC).date()
    with engine.connect() as connection:
        data = collect(connection)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"referentiel_{today.isoformat()}.md"
    path.write_text(render(data, today), encoding="utf-8")
    return path
