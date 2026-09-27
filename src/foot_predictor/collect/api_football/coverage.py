"""Couverture des compétitions par saison, d'après `/leagues` (rapport G.3).

`/leagues` sans paramètre renvoie, en une requête, toutes les compétitions,
leurs saisons, et pour chaque saison des drapeaux `coverage` (compositions,
événements, statistiques, joueurs, blessures, cotes...).

Cet index sert à deux choses :
- le tableau `docs/realisation/03_collecte/couverture.md` (commande `coverage`),
  qui permet de confirmer les identifiants configurés ;
- le planificateur, qui ne crée pas de tâche pour une saison inexistante ou
  non couverte (ADR-0002 : on ne collecte pas une saison sans compositions).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football.tasks import leagues_task
from foot_predictor.rawstore.store import latest_version, read_envelope

# (colonne du tableau, chemin du drapeau dans `coverage`)
COVERAGE_COLUMNS = [
    ("Événements", "fixtures.events"),
    ("Compositions", "fixtures.lineups"),
    ("Stats matchs", "fixtures.statistics_fixtures"),
    ("Stats joueurs", "fixtures.statistics_players"),
    ("Joueurs", "players"),
    ("Blessures", "injuries"),
    ("Classement", "standings"),
    ("Cotes", "odds"),
    ("Prédictions", "predictions"),
]


def lookup_flag(coverage: dict, path: str) -> bool | None:
    value: object = coverage
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value if isinstance(value, bool) else None


@dataclass
class LeagueCoverage:
    league_id: int
    name: str
    country: str | None
    kind: str | None
    seasons: dict[int, dict] = field(default_factory=dict)  # année -> saison complète

    def has_season(self, year: int) -> bool:
        return year in self.seasons

    def flag(self, year: int, path: str) -> bool | None:
        season = self.seasons.get(year)
        if season is None:
            return None
        return lookup_flag(season.get("coverage") or {}, path)


def coverage_from_body(body: dict) -> dict[int, LeagueCoverage]:
    index: dict[int, LeagueCoverage] = {}
    for item in body.get("response") or []:
        league = item.get("league") or {}
        if "id" not in league:
            continue
        entry = LeagueCoverage(
            league_id=league["id"],
            name=league.get("name", "?"),
            country=(item.get("country") or {}).get("name"),
            kind=league.get("type"),
        )
        for season in item.get("seasons") or []:
            if "year" in season:
                entry.seasons[int(season["year"])] = season
        index[entry.league_id] = entry
    return index


def latest_leagues_file(raw_dir: Path) -> Path | None:
    task = leagues_task("P0")
    return latest_version(raw_dir, task.rel_dir, task.stem)


def load_coverage(raw_dir: Path) -> dict[int, LeagueCoverage] | None:
    """Index tiré de la dernière réponse `/leagues` stockée, ou None."""
    path = latest_leagues_file(raw_dir)
    if path is None:
        return None
    return coverage_from_body(read_envelope(path)["body"])


def _yes_no(value: bool | None) -> str:
    return {True: "oui", False: "non", None: "?"}[value]


def render_markdown(
    coverage: dict[int, LeagueCoverage],
    tiers: dict[str, list],
    *,
    status_body: dict | None,
    source_file: str,
    generated_at: dt.datetime,
) -> str:
    """Tableau de couverture des compétitions configurées, palier par palier.

    Seules les informations d'abonnement utiles sont reprises de `/status`
    (formule, fin, quota) : jamais le nom ni l'adresse du compte.
    """
    lines = [
        "# Couverture API-FOOTBALL par compétition et par saison",
        "",
        f"Généré le {generated_at:%Y-%m-%d %H:%M} UTC par "
        "`python -m foot_predictor.collect.api_football coverage`, "
        f"à partir de `data/raw/{source_file}`. Ne pas modifier à la main : relancer la commande.",
        "",
    ]
    subscription = ((status_body or {}).get("response") or {}) if status_body else {}
    if isinstance(subscription, dict) and subscription:
        sub = subscription.get("subscription") or {}
        req = subscription.get("requests") or {}
        lines += [
            "## Abonnement (`/status`)",
            "",
            f"- Formule : {sub.get('plan', '?')} ; active : {_yes_no(sub.get('active'))} ; fin : {sub.get('end', '?')}",
            f"- Requêtes consommées aujourd'hui : {req.get('current', '?')} / {req.get('limit_day', '?')}",
            "",
        ]

    lines += ["## Synthèse des identifiants configurés", ""]
    lines += [
        "| Palier | Bloc | Id | Nom (API) | Pays | Type | Saisons | Saisons avec compositions |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for tier, blocks in tiers.items():
        for block in blocks:
            for league_id in block.leagues:
                cov = coverage.get(league_id)
                if cov is None:
                    lines.append(f"| {tier} | {block.name} | {league_id} | ⚠️ absent de /leagues | | | | |")
                    continue
                years = sorted(cov.seasons)
                with_lineups = [y for y in years if cov.flag(y, "fixtures.lineups")]
                lines.append(
                    f"| {tier} | {block.name} | {league_id} | {cov.name} | {cov.country or ''} | {cov.kind or ''} | "
                    f"{_span(years)} | {_span(with_lineups)} |"
                )
    lines.append("")

    lines += ["## Détail par compétition", ""]
    seen: set[int] = set()
    for tier, blocks in tiers.items():
        for block in blocks:
            for league_id in block.leagues:
                if league_id in seen or league_id not in coverage:
                    continue
                seen.add(league_id)
                cov = coverage[league_id]
                lines += [f"### {league_id} : {cov.name} ({cov.country or '?'}, {cov.kind or '?'})", ""]
                header = ["Saison", "Début", "Fin"] + [label for label, _ in COVERAGE_COLUMNS]
                lines.append("| " + " | ".join(header) + " |")
                lines.append("|" + "---|" * len(header))
                for year in sorted(cov.seasons):
                    season = cov.seasons[year]
                    cells = [str(year), season.get("start", ""), season.get("end", "")]
                    cells += [_yes_no(cov.flag(year, path)) for _, path in COVERAGE_COLUMNS]
                    lines.append("| " + " | ".join(cells) + " |")
                lines.append("")
    return "\n".join(lines)


def _span(years: list[int]) -> str:
    if not years:
        return "aucune"
    if years == list(range(years[0], years[-1] + 1)):
        return f"{years[0]}-{years[-1]} ({len(years)})"
    return ", ".join(str(y) for y in years) + f" ({len(years)})"
