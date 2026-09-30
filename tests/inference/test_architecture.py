"""Architecture : `inference/` lit les matchs par la porte `features/sources.py`, jamais `staging` directement."""

from __future__ import annotations

import re
from pathlib import Path

INFERENCE = Path(__file__).resolve().parents[2] / "src" / "foot_predictor" / "inference"


def test_inference_never_queries_staging_directly():
    offenders = [
        p.name
        for p in sorted(INFERENCE.rglob("*.py"))
        if re.search(r"staging\.|from foot_predictor\.db\.models import .*\bMatch\b", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
