"""Mise en forme des réponses de l'API pour l'interface : fonctions pures, sans Streamlit, testables seules.

L'interface n'a aucune logique métier : elle **traduit** le contrat de l'API (statuts, loi du total,
matrice de disponibilité) en libellés, tableaux et textes. Les statuts reprennent ceux du schéma
`Status` de l'API (décision 6 de la partie 5) :

| Statut | Pastille | Bouton « Prédiction » |
|---|---|---|
| `available` | 🟢 disponible | actif |
| `unavailable` | 🔴 indisponible (raisons) | inactif |
| `out_of_scope` | ⚪ hors périmètre du modèle H1 | inactif |
| `excluded` | ⚫ match exclu | inactif |
| `h2_unavailable` | 🟣 H2 non disponible | inactif |
"""

from __future__ import annotations

import pandas as pd

STATUS_BADGES = {
    "available": "🟢 disponible",
    "unavailable": "🔴 indisponible",
    "out_of_scope": "⚪ hors périmètre",
    "excluded": "⚫ exclu",
    "h2_unavailable": "🟣 H2 non disponible",
}
STATUS_LEGEND = {
    "available": "toutes les variables requises du modèle sont présentes : prédiction possible",
    "unavailable": "au moins une variable requise est manquante ou périmée : aucune prédiction",
    "out_of_scope": "D2, coupe, barrage ou autre championnat : le modèle H1 ne couvre que le top 5",
    "excluded": "match annulé, abandonné ou sur tapis vert (ADR-0009)",
    "h2_unavailable": "horizon H2 (avec composition) : pas avant la partie 6",
}
VARIABLE_BADGES = {"presente": "🟢 présente", "manquante": "🔴 manquante", "perimee": "🟠 périmée"}
SIDES = {"domicile": "domicile", "exterieur": "extérieur"}
K_LABELS = [str(k) for k in range(10)] + ["10+"]


def badge(status: str) -> str:
    return STATUS_BADGES.get(status, f"? {status}")


def can_predict(match: dict) -> bool:
    """Le bouton « Prédiction » n'est actif que si l'API dit toutes les variables présentes."""
    return match.get("status") == "available"


def reasons_text(match: dict) -> str:
    return " ; ".join(match.get("reasons") or [])


def kickoff_label(match: dict) -> str:
    """Heure du coup d'envoi en UTC (« 19:00 UTC ») ou « heure inconnue »."""
    kickoff = match.get("kickoff_utc")
    if not kickoff:
        return "heure inconnue"
    return f"{pd.Timestamp(kickoff).strftime('%H:%M')} UTC"


def matches_frame(matches: list[dict]) -> pd.DataFrame:
    """Tableau de l'écran « Matchs » : une ligne par match, pastille et raisons en clair."""
    rows = [
        {
            "Heure": kickoff_label(m),
            "Championnat": m.get("competition") or str(m.get("competition_id")),
            "Domicile": m.get("home_team") or str(m.get("home_team_id")),
            "Extérieur": m.get("away_team") or str(m.get("away_team_id")),
            "Disponibilité": badge(m["status"]),
            "Raisons": reasons_text(m),
        }
        for m in matches
    ]
    return pd.DataFrame(rows, columns=["Heure", "Championnat", "Domicile", "Extérieur", "Disponibilité", "Raisons"])


def status_counts(matches: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in matches:
        counts[m["status"]] = counts.get(m["status"], 0) + 1
    return counts


def competition_label(competition: dict) -> str:
    """« Premier League (England) » ; « · hors périmètre » pour ce que le modèle H1 ne couvre pas."""
    name = competition.get("name") or f"championnat {competition['id']}"
    country = f" ({competition['country']})" if competition.get("country") else ""
    scope = "" if competition.get("in_model_scope") else " · hors périmètre"
    return f"{name}{country}{scope}"


def distribution_frame(prediction: dict) -> pd.DataFrame:
    """P(T = k) pour k de 0 à 9 et « 10+ », dans cet ordre, et l'appartenance à l'intervalle annoncé."""
    distribution = prediction["total_distribution"]
    interval = prediction["interval"]
    low, high = interval["low"], interval["high"]
    rows = []
    for position, label in enumerate(K_LABELS):
        inside = low <= position <= high
        rows.append(
            {
                "Buts": label,
                "Probabilité": float(distribution[label]),
                "Intervalle": "dans [q10 ; q90]" if inside else "hors intervalle",
            }
        )
    return pd.DataFrame(rows)


def interval_text(prediction: dict) -> str:
    """« [1 ; 4] buts, couverture annoncée 79,3 % » : l'intervalle n'a de sens qu'avec sa couverture."""
    interval = prediction["interval"]
    coverage = percent(interval["announced_coverage"])
    return f"[{interval['low']} ; {interval['high_label']}] buts, couverture annoncée {coverage}"


def percent(p: float | None, digits: int = 1) -> str:
    if p is None:
        return "n. d."
    return f"{100 * p:.{digits}f} %".replace(".", ",")


def number(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "n. d."
    return f"{x:.{digits}f}".replace(".", ",")


def variables_frame(variables: list[dict]) -> pd.DataFrame:
    """Matrice de disponibilité : une ligne par (variable, côté), valeur utilisée ou raison de l'absence."""
    rows = [
        {
            "Variable": v["variable"],
            "Côté": SIDES.get(v["side"], v["side"]),
            "Statut": VARIABLE_BADGES.get(v["status"], v["status"]),
            "Valeur": "" if v.get("value") is None else number(float(v["value"]), 3),
            "Raison": v.get("reason") or "",
            "Date de la source": v.get("source_date") or "",
        }
        for v in variables
    ]
    return pd.DataFrame(rows, columns=["Variable", "Côté", "Statut", "Valeur", "Raison", "Date de la source"])


def actual_total(answer: dict) -> int | None:
    score = answer.get("actual_score") or {}
    if score.get("home") is None or score.get("away") is None:
        return None
    return int(score["home"]) + int(score["away"])


def actual_score_text(answer: dict) -> str | None:
    """Score réel du rejeu et probabilité que le modèle donnait à ce total (case « 10+ » au-delà de 9)."""
    total = actual_total(answer)
    if total is None:
        return None
    score = answer["actual_score"]
    text = f"{score['home']} – {score['away']} (total {total})"
    prediction = answer.get("prediction")
    if prediction:
        label = str(total) if total < 10 else "10+"
        text += f" ; le modèle donnait P(T = {label}) = {percent(prediction['total_distribution'][label])}"
    return text


def problem_title(status: int | None) -> str:
    """Titre lisible d'une erreur de l'API (le message détaillé de l'API suit)."""
    return {
        None: "API injoignable",
        403: "Date refusée (saison scellée ou non ouverte au rejeu)",
        404: "Match inconnu",
        409: "Prédiction impossible : match indisponible",
        422: "Requête invalide",
        501: "Non disponible avant la partie 6",
        503: "Modèle actif indisponible",
    }.get(status, f"Erreur de l'API (HTTP {status})")


def card_summary(card: dict) -> list[tuple[str, str]]:
    """Carte d'identité du modèle actif : lignes (rubrique, valeur) lisibles, sans chemin de fichier."""
    model = card.get("model", {})
    training = card.get("training", {})
    dataset = card.get("dataset", {})
    chosen = (card.get("hyperparameters") or {}).get("chosen") or model.get("params") or {}
    rows = [
        ("Version", card.get("version", "n. d.")),
        ("Horizon", card.get("horizon", "n. d.")),
        ("Structure", f"{model.get('class', '?')} ({model.get('id', '?')})"),
        ("Hyperparamètres retenus", ", ".join(f"{k} = {v}" for k, v in chosen.items()) or "n. d."),
        ("Créé le", str(card.get("created_at", "n. d."))),
    ]
    if training:
        seasons = f"{training.get('first_season')}-{training.get('last_season')}"
        rows += [
            ("Saisons d'apprentissage", f"{seasons} (année de début de saison)"),
            ("Matchs d'apprentissage", f"{training.get('matches')} ({training.get('population')})"),
            ("Contient des matchs scellés", "oui" if training.get("includes_sealed_matches") else "non"),
        ]
    if dataset:
        rows.append(("Jeu de données", str(dataset.get("version"))))
    return rows


def validation_frame(card: dict) -> pd.DataFrame:
    """Métriques de validation (plis de développement, protocole de l'ADR-0037) de la carte."""
    validation = card.get("validation") or {}
    metrics = [
        ("Log-loss du total", validation.get("log_loss"), 4),
        ("RPS", validation.get("rps"), 4),
        ("Brier P(T > 2,5)", validation.get("brier_over_2_5"), 4),
    ]
    rows = [{"Métrique": name, "Valeur": number(value, digits)} for name, value, digits in metrics if value is not None]
    calibration = validation.get("calibration_over_2_5") or {}
    if calibration.get("slope") is not None:
        rows.append({"Métrique": "Pente de calibration P(T > 2,5)", "Valeur": number(calibration["slope"], 2)})
    if validation.get("matches") is not None:
        rows.append({"Métrique": "Matchs évalués", "Valeur": str(validation["matches"])})
    if validation.get("folds"):
        rows.append({"Métrique": "Plis", "Valeur": ", ".join(validation["folds"])})
    return pd.DataFrame(rows, columns=["Métrique", "Valeur"])


def comparisons_frame(card: dict) -> pd.DataFrame:
    """Écarts de log-loss appariés avec leurs IC 95 % (A − B > 0 : B est meilleur)."""
    rows = []
    for comparison in (card.get("validation") or {}).get("comparisons") or []:
        log_loss = comparison.get("log_loss") or {}
        low, high = log_loss.get("low"), log_loss.get("high")
        excludes = log_loss.get("excludes_zero")
        rows.append(
            {
                "Comparaison": f"{comparison.get('a')} − {comparison.get('b')}",
                "Écart de log-loss": number(log_loss.get("mean"), 4),
                "IC 95 %": f"[{number(low, 4)} ; {number(high, 4)}]" if low is not None else "n. d.",
                "Significatif": {True: "oui (IC sans 0)", False: "non"}.get(excludes, "n. d."),
            }
        )
    return pd.DataFrame(rows, columns=["Comparaison", "Écart de log-loss", "IC 95 %", "Significatif"])


def limits_list(card: dict) -> list[str]:
    limits = card.get("limits") or []
    return [str(item) for item in limits] if isinstance(limits, list) else [str(limits)]
