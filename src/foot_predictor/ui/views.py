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
    "h2_unavailable": "horizon H2 (avec composition) demandé en live : les compositions ne sont plus fournies",
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


XI_VARIABLES = {
    "xi_quality": "Qualité du onze (note rétrécie)",
    "xi_regulars_missing": "Part des habituels absents",
    "xi_mean_age": "Âge moyen du onze (ans)",
}
"""Variables de G5 que la page « Détail » montre pour les deux équipes (les seules qui changent la prédiction de H2)."""


def h2_difference_frame(h1: dict, h2: dict) -> pd.DataFrame:
    """Ce que la composition change : H1, H2 et leur écart, pour E[T], λ et P(T > 2,5). Les deux réponses ont une
    prédiction ; l'écart est H2 − H1 (positif : H2 attend plus de buts)."""
    first, second = h1["prediction"], h2["prediction"]
    rows = []
    for label, key, as_percent in (
        ("E[T] (buts attendus)", "expected_total", False),
        ("λ domicile", "lambda_home", False),
        ("λ extérieur", "lambda_away", False),
        ("P(T > 2,5)", "p_over_2_5", True),
    ):
        a, b = first[key], second[key]
        if as_percent:
            rows.append({"Grandeur": label, "H1": percent(a), "H2": percent(b),
                         "Écart H2 − H1": f"{100 * (b - a):+.1f} points".replace(".", ",")})  # fmt: skip
        else:
            rows.append({"Grandeur": label, "H1": number(a), "H2": number(b),
                         "Écart H2 − H1": f"{b - a:+.2f}".replace(".", ",")})  # fmt: skip
    return pd.DataFrame(rows, columns=["Grandeur", "H1", "H2", "Écart H2 − H1"])


def composition_frame(variables: list[dict]) -> pd.DataFrame:
    """Valeurs de G5 des deux équipes, telles que le modèle H2 les a lues (vide : variable manquante)."""
    values = {(v["variable"], v["side"]): v for v in variables}
    rows = []
    for name, label in XI_VARIABLES.items():
        row = {"Variable": label}
        for side, title in (("domicile", "Domicile"), ("exterieur", "Extérieur")):
            found = values.get((name, side))
            if found is None:
                row[title] = ""
            elif found.get("value") is None:
                row[title] = "manquante"
            else:
                row[title] = number(float(found["value"]), 3)
        rows.append(row)
    return pd.DataFrame(rows, columns=["Variable", "Domicile", "Extérieur"])


def gain_text(item: dict) -> str:
    """« +0,00078 [+0,00003 ; +0,00151] » : écart de log-loss et son intervalle à 95 %."""

    def signed(x: float) -> str:
        return f"{x:+.5f}".replace(".", ",").replace("-", "−")

    return f"{signed(item['gain'])} [{signed(item['low'])} ; {signed(item['high'])}]"


def contribution_steps_frame(contribution: dict) -> pd.DataFrame:
    rows = [
        {
            "Étape": step["step"],
            "Groupe": f"{step['group']} · {step['label']}",
            "Ajouté à": step["added_to"],
            "Gain de log-loss [IC 95 %]": gain_text(step),
            "Plis gagnés": f"{step['folds_won']} sur {step['folds']}",
            "Verdict": "retenu" if step["retained"] else "non retenu",
        }
        for step in contribution["steps"]
    ]
    return pd.DataFrame(
        rows, columns=["Étape", "Groupe", "Ajouté à", "Gain de log-loss [IC 95 %]", "Plis gagnés", "Verdict"]
    )


def contribution_other_frame(items: list[dict], decisions: bool = False) -> pd.DataFrame:
    """Diagnostics et structures : un libellé, le gain avec son intervalle, les plis gagnés."""
    rows = []
    for item in items:
        row = {"Comparaison": item["label"], "Gain de log-loss [IC 95 %]": gain_text(item),
               "Plis gagnés": f"{item['folds_won']} sur {item['folds']}"}  # fmt: skip
        if decisions:
            row["Remplace M3"] = "oui" if item["replaces"] else "non"
        rows.append(row)
    columns = ["Comparaison", "Gain de log-loss [IC 95 %]", "Plis gagnés"] + (["Remplace M3"] if decisions else [])
    return pd.DataFrame(rows, columns=columns)


def contribution_rounds_frame(rounds: list[dict]) -> pd.DataFrame:
    rows = [
        {"Journées": r["rounds"], "Matchs": r["n"], "Gain de G5 [IC 95 %]": gain_text(
            {"gain": r["mean"], "low": r["low"], "high": r["high"]}
        ), "Intervalle sans 0": "oui" if r["excludes_zero"] else "non"}
        for r in rounds
    ]  # fmt: skip
    return pd.DataFrame(rows, columns=["Journées", "Matchs", "Gain de G5 [IC 95 %]", "Intervalle sans 0"])


def problem_title(status: int | None) -> str:
    """Titre lisible d'une erreur de l'API (le message détaillé de l'API suit)."""
    return {
        None: "API injoignable",
        403: "Date refusée (saison scellée ou non ouverte au rejeu)",
        404: "Match inconnu",
        409: "Prédiction impossible : match indisponible",
        422: "Requête invalide",
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
