"""Gel des données (ADR-0005, ADR-0006) : quelques étapes sûres, dans l'ordre.

    uv run python -m foot_predictor.collect.api_football --raw-dir C:/foot-predictor/data/raw freeze \\
        --dest D:/foot-predictor/data-freeze-2026-10/raw --restore-to C:/fp_restauration/raw

1. **Verrou** : la commande prend le verrou de collecte. Si une collecte ou
   une tâche planifiée tourne, elle s'arrête aussitôt, sans rien copier.
2. **Contrôle** : `raw_check` sur tous les paliers. Un verdict BLOQUANT arrête
   le gel, sauf `--allow-blocking` : un trou se recollecte avant le gel,
   pas après.
3. **Sauvegarde** : copie vers `--dest` (dossier absent ou vide), puis
   vérification de chaque sha256 du journal.
4. **Test de restauration** : recopie depuis `--dest` vers `--restore-to`
   (dossier absent ou vide), puis nouvelle vérification. Le nombre de
   fichiers vérifiés doit être le même aux trois endroits.
5. **Brouillon de `DATA_FREEZE.md`** : périmètre, volumes, trous connus,
   quota consommé, sha256 du journal. Il est relu à la main avant commit.

La commande n'envoie aucune requête et n'écrit rien dans le dossier brut (à
part le verrou, retiré à la fin). Elle ne pose pas de tag Git.
"""
from __future__ import annotations

import datetime as dt
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE
from foot_predictor.collect.api_football.plan import CollectConfig
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.quality import raw_check
from foot_predictor.rawstore.backup import VerifyReport, backup
from foot_predictor.rawstore.manifest import MANIFEST_DIR, read_entries
from foot_predictor.rawstore.store import SUFFIX, sha256_file


class FreezeError(RuntimeError):
    """Étape du gel en échec : la suite n'est pas lancée."""


@dataclass
class FreezeReport:
    started_at: dt.datetime
    raw_dir: Path
    dest: Path
    restore_to: Path
    durations: dict[str, float] = field(default_factory=dict)  # étape -> secondes
    check: raw_check.CheckResult | None = None
    summary_path: Path | None = None
    saved: VerifyReport | None = None
    restored: VerifyReport | None = None
    source_files: int = 0


def _timed(report: FreezeReport, step: str, func, *args):
    start = time.perf_counter()
    try:
        return func(*args)
    finally:
        report.durations[step] = time.perf_counter() - start


def run_freeze(config: CollectConfig, raw_dir: Path, dest: Path, restore_to: Path, report_dir: Path,
               *, allow_blocking: bool = False, now: dt.datetime | None = None) -> FreezeReport:
    """Étapes 2 à 4 (le verrou est pris par la CLI). Lève `FreezeError` à la première étape en échec."""
    raw_dir, dest, restore_to = Path(raw_dir), Path(dest), Path(restore_to)
    report = FreezeReport(now or dt.datetime.now(dt.timezone.utc), raw_dir, dest, restore_to)
    report.source_files = sum(1 for _ in raw_dir.rglob(f"*{SUFFIX}"))

    tiers = list(config.tiers)
    check = _timed(report, "raw_check", lambda: raw_check.RawChecker(raw_dir, config, tiers).run(now=report.started_at))
    report.check = check
    summary, details = raw_check.report_paths(report_dir, tiers, True, check.generated_at)
    details.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(raw_check.render_summary(check, "freeze (raw_check, tous les paliers)", details.name),
                       encoding="utf-8")
    details.write_text(raw_check.render_details(check, "freeze (raw_check, tous les paliers)"), encoding="utf-8")
    report.summary_path = summary
    if check.verdict == raw_check.BLOCK and not allow_blocking:
        raise FreezeError(f"raw_check : verdict BLOQUANT (voir {summary}). Recollecter avant le gel, "
                          "ou relancer avec --allow-blocking après décision écrite.")

    report.saved = _timed(report, "sauvegarde", backup, raw_dir, dest)
    if not report.saved.ok:
        raise FreezeError(f"Sauvegarde vers {dest} : {len(report.saved.mismatched)} sha256 différent(s), "
                          f"{len(report.saved.missing)} fichier(s) absent(s). Copie non valide.")
    report.restored = _timed(report, "restauration", backup, dest, restore_to)
    if not report.restored.ok or report.restored.verified != report.saved.verified:
        raise FreezeError(f"Test de restauration vers {restore_to} en échec : {report.restored.verified} fichiers "
                          f"vérifiés contre {report.saved.verified} sauvegardés.")
    return report


# --- brouillon de DATA_FREEZE.md --------------------------------------------------------


def _size(paths) -> int:
    return sum(path.stat().st_size for path in paths)


def _mb(size: int) -> str:
    return f"{size / 1_000_000:.1f} Mo"


def request_type(relative: str) -> str:
    """Type de requête d'après le chemin du fichier : `api_football/<type>/...`.
    Le journal T-60 (`daily/<jour>/<sous-type>`) est regroupé en `daily`."""
    parts = relative.split("/")
    return parts[1] if len(parts) > 2 else relative


def public_params(params: dict) -> str:
    """Paramètres d'une tâche, sans identifiant de joueur (document versionné)."""
    return str({key: ("…" if key in ("player", "players") else value) for key, value in params.items()})


def render_data_freeze(report: FreezeReport, config: CollectConfig) -> str:
    """Brouillon de `docs/DATA_FREEZE.md`. Uniquement des nombres : aucun nom
    ni identifiant de joueur, aucun score (scellé, ADR-0012)."""
    raw_dir, check = report.raw_dir, report.check
    entries = read_entries(raw_dir, SOURCE)
    manifest = raw_dir / MANIFEST_DIR / f"{SOURCE}.jsonl"
    files = sorted(raw_dir.rglob(f"*{SUFFIX}"))
    per_type_files = Counter(request_type(p.relative_to(raw_dir).as_posix()) for p in files)
    per_type_size: Counter = Counter()
    for path in files:
        per_type_size[request_type(path.relative_to(raw_dir).as_posix())] += path.stat().st_size
    per_day = Counter(str(e.get("timestamp", ""))[:10] for e in entries)
    with WorkQueue.in_raw_dir(raw_dir) as queue:
        counts = queue.counts()
        deferred = queue.deferred_summary()
        problems = queue.problems(50)
    deferred_text = ", ".join(f"{status or '?'} {n}" for status, n in deferred)
    per_tier: dict[str, Counter] = {}
    for tier, task_type, status, count in counts:
        per_tier.setdefault(tier, Counter())[status] += count

    lines = [
        "# Gel des données API-FOOTBALL (octobre 2026)",
        "",
        f"> **Brouillon généré le {report.started_at:%Y-%m-%d %H:%M} UTC** par la commande `freeze`. "
        "À relire, compléter (sections « À compléter ») et committer ; le tag `data-freeze-2026-10` "
        "se pose après le commit.",
        "",
        "Décisions : ADR-0002 (périmètre), ADR-0003 (format), ADR-0005 (calendrier), ADR-0006 (sauvegarde), "
        "ADR-0008 (identifiants), ADR-0012 (scellé). Ce document ne contient que des nombres : aucun nom, "
        "aucun identifiant de joueur, aucun résultat de match.",
        "",
        "## Périmètre",
        "",
        "| Palier | Bloc | Compétitions | Saisons | Types |",
        "|---|---|---|---|---|",
    ]
    for tier, blocks in config.tiers.items():
        for block in blocks:
            seasons = f"{block.seasons.first or '…'} → {block.seasons.last}"
            if block.seasons.requires_coverage:
                seasons += f" (si {block.seasons.requires_coverage})"
            lines.append(f"| {tier} | {block.name} | {', '.join(map(str, block.leagues))} | {seasons} | "
                         f"{', '.join(block.endpoints)} |")
    to_detail = sum(s.to_detail for s in check.seasons)
    detailed = sum(s.detailed for s in check.seasons)
    lines += [
        "",
        "Hors YAML : profils ciblés (`player_profiles`, ADR-0008) et journal T-60 (`daily`, ADR-0010).",
        "",
        "## Volumes",
        "",
        f"- Fichiers bruts : **{len(files)}**, {_mb(_size(files))} compressés.",
        f"- Lignes du journal de requêtes : {len(entries)}.",
        f"- Matchs terminés avec détail : **{detailed} / {to_detail}**.",
        f"- Profils joueurs lus : {len(check.profiles)} ; titulaires sans date de naissance : "
        f"{sum(len(v) for v in check.starters_without_birth.values())}.",
        "",
        "| Type de requête | Fichiers | Taille |",
        "|---|---|---|",
        *(f"| {kind} | {per_type_files[kind]} | {_mb(per_type_size[kind])} |" for kind in sorted(per_type_files)),
        "",
        "| Palier | Tâches done | failed | suspect | pending |",
        "|---|---|---|---|---|",
        *(f"| {tier} | {c['done']} | {c['failed']} | {c['suspect']} | {c['pending']} |"
          for tier, c in sorted(per_tier.items())),
        "",
        "## Contrôle du brut",
        "",
        f"Verdict `raw_check` (tous les paliers) : **{check.verdict}**. Résumé versionné : "
        f"`{report.summary_path.as_posix() if report.summary_path else '?'}`.",
        "",
        "| Contrôle | Statut | Détail |",
        "|---|---|---|",
        *(f"| {line.label} | {line.status} | {line.detail} |" for line in check.checks),
        "",
        "## Trous connus",
        "",
        "Rien n'est recollecté après le gel. Les points ci-dessous sont des données telles que l'API les fournit.",
        "",
        *(f"- Tâche {row.status} : {row.tier} {row.task_type} {public_params(row.params)} ({row.last_error})"
          for row in problems),
        f"- Matchs non terminaux au gel : {sum(n for _, n in deferred)} ({deferred_text}).",
        "- Constats détaillés : `docs/realisation/05_controle_qualite/constats_P1_P2.md`, `constats_P3.md`, "
        "`constats_collisions.md`.",
        "- À compléter : MLS 2017 (constats P3, section c), bilan du journal T-60 (`t60-report`).",
        "",
        "## Quota consommé",
        "",
        f"Requêtes journalisées : **{len(entries)}**, du {min(per_day)} au {max(per_day)} (UTC).",
        "",
        "| Jour (UTC) | Requêtes |",
        "|---|---|",
        *(f"| {day} | {n} |" for day, n in sorted(per_day.items())),
        "",
        "## Journal et sauvegarde",
        "",
        f"- Journal : `{manifest.relative_to(raw_dir).as_posix()}`, sha256 `{sha256_file(manifest)}`.",
        f"- Sauvegarde : `{report.dest.as_posix()}`, {report.saved.verified} fichiers aux sha256 conformes "
        f"({len(report.saved.unlisted)} hors journal).",
        f"- Test de restauration : `{report.restore_to.as_posix()}`, {report.restored.verified} fichiers conformes.",
        "- Durées : " + ", ".join(f"{step} {seconds:.0f} s" for step, seconds in report.durations.items()) + ".",
        "",
        "## À compléter à la main",
        "",
        "- Date et heure du gel, commit et tag `data-freeze-2026-10`.",
        "- Renouvellement automatique de l'abonnement : coupé le …",
        "- Seconde copie hors de la maison (facultative, ADR-0006) : …",
        "- Tâches planifiées supprimées (`creer_taches.py --delete`) : …",
        "",
    ]
    return "\n".join(lines)
