"""Faux API pour les tests de l'interface : un `httpx.MockTransport` qui répond comme l'API (rapport F.6).

Réponses écrites à la main, au format des schémas de `api/schemas.py`, sur des matchs inventés de
2023-24 : aucune donnée réelle, aucun réseau. `calls` garde la trace des requêtes reçues.
"""

from __future__ import annotations

import httpx

DAY = "2024-03-09"
SEALED_DAY = "2025-08-16"
K_LABELS = [str(k) for k in range(10)] + ["10+"]
DISTRIBUTION = [0.06, 0.16, 0.23, 0.22, 0.16, 0.09, 0.045, 0.02, 0.01, 0.004, 0.001]


def summary(match_id: int, status: str, reasons: list[str], *, league: str = "Ligue A", api_league_id: int = 39):
    return {
        "match_id": match_id, "date": DAY, "kickoff_utc": "2024-03-09T15:00:00+00:00", "competition_id": 1,
        "api_league_id": api_league_id, "competition": league, "season": 2023, "round": "Journée 27",
        "home_team_id": 10 * match_id, "away_team_id": 10 * match_id + 1,
        "home_team": f"Équipe {match_id}A", "away_team": f"Équipe {match_id}B",
        "mode": "replay", "horizon": "H1", "status": status, "reasons": reasons,
        "model_version": "rejeu-2023-essai", "data_version": "load_run-9", "data_complete_until": "2024-03-08",
    }  # fmt: skip


MATCHES = [
    summary(1, "available", []),
    summary(2, "unavailable", ["goals_for_ewm_h240 (domicile) : pas d'historique de championnat sur 730 jours"]),
    summary(3, "out_of_scope", ["hors périmètre du modèle H1 (D2) : pas de prédiction"], league="Ligue B",
            api_league_id=40),
]  # fmt: skip

VARIABLES_OK = [
    {"variable": "elo_pre", "side": "domicile", "status": "presente", "value": 1612.5},
    {"variable": "elo_pre", "side": "exterieur", "status": "presente", "value": 1498.25},
]
VARIABLES_MISSING = [
    {"variable": "elo_pre", "side": "domicile", "status": "presente", "value": 1500.0},
    {"variable": "goals_for_ewm_h240", "side": "domicile", "status": "manquante", "value": None,
     "reason": "pas d'historique de championnat sur 730 jours"},
]  # fmt: skip

PREDICTION = {
    "lambda_home": 1.62, "lambda_away": 1.11, "expected_total": 2.73,
    "total_distribution": dict(zip(K_LABELS, DISTRIBUTION, strict=True)), "p_over_2_5": 0.55,
    "interval": {"low": 1, "high": 4, "high_label": "4", "announced_coverage": 0.77},
}  # fmt: skip

H2_REASON = "horizon H2 (avec composition) : non disponible en live (ADR-0010)"
VARIABLES_H2 = [
    *VARIABLES_OK,
    {"variable": "xi_quality", "side": "domicile", "status": "presente", "value": 7.125},
    {"variable": "xi_quality", "side": "exterieur", "status": "presente", "value": 6.98},
    {"variable": "xi_regulars_missing", "side": "domicile", "status": "presente", "value": 0.18},
    {"variable": "xi_regulars_missing", "side": "exterieur", "status": "manquante", "value": None,
     "reason": "moins de 10 matchs d'historique avec onze complet"},
    {"variable": "xi_mean_age", "side": "domicile", "status": "presente", "value": 26.4},
    {"variable": "xi_mean_age", "side": "exterieur", "status": "presente", "value": 27.9},
]  # fmt: skip
PREDICTION_H2 = {
    "lambda_home": 1.70, "lambda_away": 1.05, "expected_total": 2.75,
    "total_distribution": dict(zip(K_LABELS, DISTRIBUTION, strict=True)), "p_over_2_5": 0.57,
    "interval": {"low": 1, "high": 4, "high_label": "4", "announced_coverage": 0.77},
}  # fmt: skip


def gain(value, low, high, won=4, excludes=True):
    return {"gain": value, "low": low, "high": high, "excludes_zero": excludes, "folds_won": won, "folds": 4,
            "matches": 7123}  # fmt: skip


CONTRIBUTION = {
    "model": "M3 (Poisson par équipe) sur G0 + G1 + G2 + G5",
    "unit": "écart de log-loss du total, en nats par match ; positif : le modèle avec le groupe est meilleur",
    "dataset": "ds-essai-h2",
    "reports": {"decision": "ablations-essai", "structures": "structures-essai"},
    "folds": "4 plis de validation glissante, saisons 2021-22 à 2024-25",
    "steps": [
        {"step": 1, "group": "G6", "label": "Stabilité du onze", "variables": "recouvrement, cohésion",
         "added_to": "base H1", "retained": False, **gain(0.00035, -0.00022, 0.00091, 3, False)},
        {"step": 2, "group": "G5", "label": "Qualité du onze", "variables": "note rétrécie, habituels absents, âge",
         "added_to": "base H1 (G6 n'étant pas retenu)", "retained": True, **gain(0.00078, 0.00003, 0.00151)},
        {"step": 3, "group": "G4", "label": "Entraîneur", "variables": "ancienneté, nouvel entraîneur",
         "added_to": "base H1 + G5", "retained": False, **gain(-0.0009, -0.00158, -0.00022, 1)},
    ],
    "diagnostics": [{"label": "G5 à fenêtre d'apprentissage égale", "against": "base dès 2016-17",
                     **gain(0.00061, -0.0001, 0.0013, 4, False)}],
    "structures": [{"label": "M7 (boosting) contre M3", "replaces": False,
                    **gain(-0.00235, -0.00444, -0.00025, 0)}],
    "g5_by_round": [{"rounds": "1-5", "mean": 0.0021, "low": 0.0002, "high": 0.0041, "n": 967, "excludes_zero": True}],
    "notes": ["Le gain de G5 est minuscule."],
}  # fmt: skip

CARD = {
    "version": "scelle-h1-essai",
    "created_at": "2026-09-30T12:00:00+00:00",
    "horizon": "H1",
    "model": {"id": "M3_G0G2", "class": "M3", "params": {"half_life": 240}, "features": ["is_home", "elo_pre"]},
    "hyperparameters": {"chosen": {"groups": ["G0", "G1", "G2"], "half_life": 240}},
    "training": {"first_season": 2015, "last_season": 2024, "matches": 100, "population": "top5",
                 "includes_sealed_matches": False},
    "dataset": {"version": "ds-essai"},
    "validation": {"log_loss": 1.8805, "rps": 0.1287, "brier_over_2_5": 0.2416, "matches": 40,
                   "folds": ["2021-22", "2022-23"], "calibration_over_2_5": {"slope": 0.95},
                   "comparisons": [{"a": "B1", "b": "M3", "log_loss": {"mean": 0.0179, "low": 0.0133,
                                    "high": 0.0226, "excludes_zero": True}}]},
    "limits": ["Horizon H1 : aucune information de composition."],
}  # fmt: skip


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.saved = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params.multi_items())
        self.calls.append((request.method, request.url.path, params))
        path, method = request.url.path, request.method
        if path == "/competitions":
            return httpx.Response(200, json=[
                {"id": 1, "name": "Ligue A", "api_league_id": 39, "country": "Pays", "kind": "league",
                 "in_model_scope": True},
                {"id": 2, "name": "Ligue B", "api_league_id": 40, "country": "Pays", "kind": "league",
                 "in_model_scope": False},
            ])  # fmt: skip
        if path == "/matches":
            if params.get("date", "") >= "2025-07-01":
                return httpx.Response(403, json={"detail": "Date 2025-08-16 sous scellés.", "reasons": []})
            return httpx.Response(200, json=MATCHES if params.get("date") == DAY else [])
        if path.startswith("/matches/"):
            match_id = int(path.split("/")[2])
            match = next((m for m in MATCHES if m["match_id"] == match_id), None)
            if match is None:
                return httpx.Response(404, json={"detail": f"Match {match_id} inconnu.", "reasons": []})
            variables = VARIABLES_OK if match["status"] == "available" else VARIABLES_MISSING
            h2 = params.get("horizon") == "H2"
            if h2 and params.get("mode") == "live":  # ADR-0010 : aucune composition en live
                match = match | {"horizon": "H2", "mode": "live", "status": "h2_unavailable", "reasons": [H2_REASON],
                                 "model_version": None}  # fmt: skip
                if path.endswith("/availability"):
                    return httpx.Response(200, json=match | {"variables": []})
                return httpx.Response(409, json={"detail": f"Match {match_id} indisponible (h2_unavailable) : "
                                                 "aucune prédiction.", "reasons": [H2_REASON]})  # fmt: skip
            if h2:
                match = match | {"horizon": "H2", "model_version": "rejeu-2023-m3_h2"}
                variables = VARIABLES_H2 if match["status"] == "available" else VARIABLES_MISSING
            if path.endswith("/availability"):
                return httpx.Response(200, json=match | {"variables": variables})
            if method == "POST" and path.endswith("/predictions"):
                if match["status"] != "available":
                    return httpx.Response(409, json={"detail": f"Match {match_id} indisponible : aucune prédiction.",
                                                     "reasons": match["reasons"]})  # fmt: skip
                self.saved += 1
                body = match | {
                    "variables": variables, "prediction": PREDICTION_H2 if h2 else PREDICTION,
                    "actual_score": {"home": 2, "away": 1},
                    "market_reference": {"p_over_2_5": 0.52, "odds_column": "avant clôture", "version": "v"},
                    "saved": {"id": 7, "created": self.saved == 1, "created_at": "2026-10-04T10:00:00+00:00"},
                }  # fmt: skip
                return httpx.Response(201 if self.saved == 1 else 200, json=body)
        if path == "/models/h2/contribution":
            return httpx.Response(200, json=CONTRIBUTION)
        if path == "/models/active":
            return httpx.Response(200, json=CARD)
        if path == "/data/freshness":
            return httpx.Response(200, json={"data_version": "load_run-9", "sources": [
                {"source": "staging", "last_update": "2026-09-30", "complete_until": "2025-06-30"}]})  # fmt: skip
        if path == "/health":
            return httpx.Response(200, json={"status": "ok", "database": "ok", "model": "scelle-h1-essai"})
        return httpx.Response(404, json={"detail": "route inconnue"})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
