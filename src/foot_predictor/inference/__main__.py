"""Inférence en ligne de commande (partie 5, ADR-0040).

    python -m foot_predictor.inference check [--only rows]

`check` : contrôles sur données réelles de la période de développement (lignes d'inférence contre
le jeu d'entraînement), rapport Markdown et JSON dans `reports/inference/`. Les commandes `predict`
et `models` arrivent aux sous-étapes 5.2 et 5.3.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.inference")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="contrôles sur données réelles (période de développement)")
    check.add_argument("--only", choices=["rows", "replay"], help="un seul contrôle")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    from foot_predictor.inference import check

    if args.command != "check":  # predict et models : sous-étapes 5.2 et 5.3
        return 2
    today = dt.datetime.now(dt.UTC).date().isoformat()
    ok = True
    if args.only in (None, "rows"):
        report = check.run_rows_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"lignes_{today}", check.render_rows(report))
        print(
            f"Lignes : {'identiques' if report['all_identical'] else 'ÉCART'} ({report['rows_compared']} lignes) ; {md_path}"
        )
        ok &= report["all_identical"]
    if args.only in (None, "replay"):
        report = check.run_replay_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"rejeu_{today}", check.render_replay(report))
        print(f"Rejeu : {'reproduit' if report['all_reproduced'] else 'ÉCART'} ; {md_path}")
        ok &= report["all_reproduced"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
