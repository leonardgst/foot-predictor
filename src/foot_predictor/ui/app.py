"""Interface Streamlit : trois écrans au-dessus de l'API locale (rapport F.7, ADR-0040).

Lancement (l'API doit tourner) :

    uv run python -m foot_predictor.api serve          # terminal 1
    uv run streamlit run src/foot_predictor/ui/app.py  # terminal 2, puis http://127.0.0.1:8501

| Écran | Contenu | Routes appelées |
|---|---|---|
| Matchs | mode, date, championnats ; pastille de disponibilité et raisons ; bouton « Prédiction » | `/competitions`, `/matches` |
| Détail | H1 (sans composition) et H2 (avec composition, rejeu) côte à côte : loi du total (barres), E[T], λ, intervalle et couverture annoncée, P(T > 2,5), variables, ce que la composition change, score réel | `POST /matches/{id}/predictions`, `/matches/{id}/availability` (`horizon=H1` et `H2`) |
| Apport des variables | gain mesuré de chaque groupe de variables H2 (G6, G5, G4), décision, structures, où se concentre le gain | `/models/h2/contribution` |
| Modèle | carte d'identité, métriques de validation, courbe d'apport, fraîcheur des données | `/models/active`, `/data/freshness`, `/health` |

L'interface ne lit **jamais** la base et n'importe aucune logique métier : tout passe par
`ui.client.ApiClient` (HTTP). Streamlit réexécute ce script de haut en bas à chaque clic ;
l'état (écran, match choisi, réponse) vit dans `st.session_state`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import streamlit as st

from foot_predictor.ui import views
from foot_predictor.ui.client import ApiClient, ApiProblem

SCREENS = ("Matchs", "Détail", "Apport des variables", "Modèle")
MODES = {"Rejeu": "replay", "Live": "live"}
DEFAULT_REPLAY_DATE = dt.date(
    2025, 5, 18
)  # journée de 2024-25 : saison de développement (le rejeu des saisons scellées est ouvert depuis ADR-0052)
FIGURE = Path(__file__).resolve().parents[3] / "docs" / "resultats" / "figures" / "courbe_apport.png"
MEMO_SIZE = 20


def show_problem(problem: ApiProblem) -> None:
    """Erreur de l'API affichée lisiblement : titre selon le statut HTTP, message de l'API, raisons."""
    text = f"**{views.problem_title(problem.status)}**\n\n{problem.detail}"
    if problem.reasons:
        text += "\n\n" + "\n".join(f"- {reason}" for reason in problem.reasons)
    st.error(text)


def cached(key: tuple, fetch):
    """Mémo par session (les réponses de `/matches` coûtent environ 1 s à chaud) ; vidé par « Rafraîchir »."""
    memo = st.session_state.setdefault("_memo", {})
    if key not in memo:
        if len(memo) >= MEMO_SIZE:
            memo.clear()
        memo[key] = fetch()  # une erreur n'est jamais mémorisée : l'exception remonte
    return memo[key]


def fetch_h2(client: ApiClient, match: dict, mode: str, predict: bool) -> dict:
    """Réponse H2 d'un match : `{"answer": ...}` ou `{"problem": ApiProblem}`. En live, l'API répond « H2 non
    disponible » (200 pour les variables, 409 pour une prédiction) : la raison s'affiche, rien n'est calculé."""
    try:
        if predict:
            return {"answer": client.predict(match["match_id"], mode, "H2")}
        return {"answer": client.availability(match["match_id"], mode, "H2")}
    except ApiProblem as problem:
        return {"problem": problem}


def open_detail(client: ApiClient, match: dict, mode: str, predict: bool) -> None:
    """Rappel d'un bouton : appelle l'API pour H1 et H2, garde les réponses ou les erreurs, puis passe à « Détail »."""
    state = st.session_state
    try:
        if predict:
            state.detail = client.predict(match["match_id"], mode)
        else:
            state.detail = client.availability(match["match_id"], mode)
        state.detail_error = None
    except ApiProblem as problem:
        state.detail, state.detail_error = None, problem
    if state.detail_error is not None and state.detail_error.status in (None, 403, 404):
        state.detail_h2 = None  # la même erreur vaudrait pour H2 (API injoignable, date scellée, match inconnu)
    else:
        state.detail_h2 = fetch_h2(client, match, mode, predict)
    state.detail_match = match
    state.screen = "Détail"


def matches_screen(client: ApiClient) -> None:
    st.header("Matchs")
    left, middle, right = st.columns([1, 1, 2])
    mode_label = left.radio(
        "Mode",
        list(MODES),
        horizontal=True,
        key="mode_label",
        help="Rejeu : matchs passés, prédits avec le modèle du pli de leur saison (2021-22 à 2026-27 ; 2025-26 et "
        "2026-27 emploient le modèle du test scellé, appris jusqu'en 2024-25, ADR-0052). Live : matchs à venir, modèle actif.",
    )
    mode = MODES[mode_label]
    default = DEFAULT_REPLAY_DATE if mode == "replay" else dt.date.today()
    date = middle.date_input("Date", value=default, key=f"date_{mode}", format="DD/MM/YYYY")

    try:
        competitions = cached(("competitions", client.base_url), client.competitions)
    except ApiProblem as problem:
        show_problem(problem)
        return
    labels = {c["id"]: views.competition_label(c) for c in competitions}
    selected = right.multiselect(
        "Championnats", list(labels), format_func=lambda i: labels.get(i, str(i)), key="competitions",
        placeholder="tous les championnats",
    )  # fmt: skip
    if st.button("Rafraîchir", help="relire l'API (nouvelles données, statut d'un match qui a changé)"):
        st.session_state.pop("_memo", None)

    key = ("matches", client.base_url, date.isoformat(), mode, tuple(sorted(selected)))
    try:
        matches = cached(key, lambda: client.matches(date, mode, selected))
    except ApiProblem as problem:
        show_problem(problem)
        return
    if not matches:
        st.info(f"Aucun match le {date:%d/%m/%Y} pour ces championnats.")
        return

    counts = views.status_counts(matches)
    summary = ", ".join(f"{n} {views.badge(status)}" for status, n in counts.items())
    st.caption(f"{len(matches)} matchs : {summary}. Survoler une pastille pour sa raison.")

    widths = [1, 2, 4, 2, 1.3, 1.3]
    for column, title in zip(st.columns(widths), ["Heure", "Championnat", "Match", "Disponibilité", "", ""]):
        column.markdown(f"**{title}**" if title else "")
    for match in matches:
        hour, league, teams, status, predict, detail = st.columns(widths, vertical_alignment="center")
        hour.write(views.kickoff_label(match))
        league.write(match.get("competition") or str(match["competition_id"]))
        teams.write(
            f"{match.get('home_team') or match['home_team_id']} – {match.get('away_team') or match['away_team_id']}"
        )
        reasons = views.reasons_text(match)
        status.markdown(views.badge(match["status"]), help=reasons or None)
        predict.button(
            "Prédiction", key=f"predict_{match['match_id']}", type="primary", disabled=not views.can_predict(match),
            help=None if views.can_predict(match) else f"indisponible : {reasons}",
            on_click=open_detail, args=(client, match, mode, True),
        )  # fmt: skip
        detail.button(
            "Variables", key=f"variables_{match['match_id']}", help="matrice de disponibilité, sans prédiction",
            on_click=open_detail, args=(client, match, mode, False),
        )  # fmt: skip

    with st.expander("Légende des pastilles et raisons", expanded=counts.get("available", 0) < len(matches)):
        for status, text in views.STATUS_LEGEND.items():
            st.markdown(f"- {views.badge(status)} : {text}")
        blocked = [m for m in matches if not views.can_predict(m)]
        if blocked:
            st.dataframe(views.matches_frame(blocked), hide_index=True)


def prediction_block(answer: dict | None, problem: ApiProblem | None, title: str, subtitle: str) -> None:
    """Une colonne de l'écran « Détail » : disponibilité, puis loi du total si le modèle a prédit."""
    st.subheader(title)
    st.caption(subtitle)
    if problem is not None:
        show_problem(problem)
        return
    if answer is None:
        st.info("Aucune réponse.")
        return
    st.markdown(f"Disponibilité : {views.badge(answer['status'])}" + (
        f" — {views.reasons_text(answer)}" if answer.get("reasons") else ""))  # fmt: skip
    prediction = answer.get("prediction")
    if prediction:
        top = st.columns(2)
        top[0].metric("E[T] (buts attendus)", views.number(prediction["expected_total"]))
        top[1].metric("P(T > 2,5)", views.percent(prediction["p_over_2_5"]))
        bottom = st.columns(2)
        bottom[0].metric("λ domicile", views.number(prediction["lambda_home"]))
        bottom[1].metric("λ extérieur", views.number(prediction["lambda_away"]))
        st.markdown(f"**Intervalle [q10 ; q90]** : {views.interval_text(prediction)}")
        st.bar_chart(
            views.distribution_frame(prediction), x="Buts", y="Probabilité", color="Intervalle", sort=False,
            x_label="nombre total de buts T", y_label="P(T = k)",
        )  # fmt: skip
    elif answer["status"] == "available":
        st.info("Toutes les variables sont présentes : le bouton « Prédiction » de l'écran « Matchs » calcule la loi.")


def variables_block(answer: dict | None, empty: str) -> None:
    variables = (answer or {}).get("variables") or []
    if variables:
        missing = sum(v["status"] != "presente" for v in variables)
        st.caption(f"{len(variables) - missing} présentes, {missing} manquantes ou périmées (aucune valeur remplacée).")
        st.dataframe(views.variables_frame(variables), hide_index=True)
    else:
        st.caption(empty)


def detail_screen() -> None:
    state = st.session_state
    st.header("Détail")
    problem: ApiProblem | None = state.get("detail_error")
    answer: dict | None = state.get("detail")
    h2: dict = state.get("detail_h2") or {}
    if problem is not None and state.get("detail_h2") is None:
        match = state.get("detail_match") or {}
        if match:
            st.subheader(f"{match.get('home_team')} – {match.get('away_team')}")
        show_problem(problem)
        return
    if not answer and problem is None:
        st.info("Choisir un match dans l'écran « Matchs » (bouton « Prédiction » ou « Variables »).")
        return

    header = answer or h2.get("answer") or state.get("detail_match") or {}
    st.subheader(f"{header.get('home_team')} – {header.get('away_team')}")
    if answer:
        mode = "rejeu" if answer["mode"] == "replay" else "live"
        st.caption(
            f"{answer.get('competition')} · {answer['date']} · {views.kickoff_label(answer)} · "
            f"saison {answer['season']}-{str(answer['season'] + 1)[-2:]} · mode {mode}"
        )
    left, right = st.columns(2)
    with left:
        prediction_block(
            answer, problem, "H1 · sans composition", "Modèle figé du MVP (ADR-0039) : Elo, forme, calendrier."
        )
    with right:
        prediction_block(
            h2.get("answer"), h2.get("problem"), "H2 · avec composition",
            "Rejeu seulement : ajoute la qualité du onze annoncé (G5). Jamais en live, faute de compositions (ADR-0010).",
        )  # fmt: skip

    h1_prediction = (answer or {}).get("prediction")
    h2_prediction = (h2.get("answer") or {}).get("prediction")
    if h1_prediction:
        actual = views.actual_score_text(answer)
        if actual:
            st.info(f"Score réel (rejeu) : {actual}")
        market = answer.get("market_reference")
        if market:
            st.caption(
                f"Référence de marché (cotes avant clôture, jamais une variable du modèle, ADR-0036) : "
                f"P(T > 2,5) implicite = {views.percent(market['p_over_2_5'])}"
            )
    if h1_prediction and h2_prediction:
        st.subheader("Ce que la composition change")
        st.dataframe(views.h2_difference_frame(answer, h2["answer"]), hide_index=True)
        st.markdown("**Qualité du onze annoncé** (variables G5 lues par H2)")
        st.dataframe(views.composition_frame(h2["answer"].get("variables") or []), hide_index=True)
        st.caption(
            "Sur l'ensemble des matchs, G5 améliore le log-loss de moins de 0,1 % (écran « Apport des variables ») : "
            "l'écart d'un match ne dit pas lequel des deux modèles avait raison."
        )

    st.subheader("Variables utilisées et manquantes")
    variables_block(answer, "Aucune variable évaluée pour ce match (hors périmètre ou exclu).")
    if h2.get("answer") and h2["answer"].get("variables"):
        with st.expander("Variables de l'horizon H2 (H1 plus la composition)"):
            variables_block(h2["answer"], "")

    lines = []
    for label, item in (("H1", answer), ("H2", h2.get("answer"))):
        if item and item.get("model_version"):
            lines.append(f"Modèle {label} : `{item['model_version']}`")
    reference = answer or h2.get("answer")
    if reference:
        lines.append(
            f"Version des données : `{reference['data_version']}` ; données complètes jusqu'au "
            f"{reference['data_complete_until']}"
        )
    for label, item in (("H1", answer), ("H2", h2.get("answer"))):
        saved = (item or {}).get("saved")
        if saved:
            origin = "créée maintenant" if saved.get("created") else "déjà tracée, renvoyée telle quelle"
            lines.append(
                f"Prédiction {label} n° {saved.get('id')} de `ops.prediction` ({origin}, {saved.get('created_at')})"
            )
    st.caption("  \n".join(lines))


def contribution_screen(client: ApiClient) -> None:
    st.header("Apport des variables")
    st.caption(
        "Que rapporte la composition officielle (onze et entraîneur) au-delà du modèle H1 ? Les chiffres viennent des "
        "rapports d'expériences par l'API, sur les 4 plis de validation (2021-22 à 2024-25, protocole figé de l'ADR-0037). "
        "Un gain positif veut dire que le modèle avec le groupe prédit mieux le total de buts."
    )
    try:
        contribution = cached(("h2_contribution", client.base_url), client.h2_contribution)
    except ApiProblem as problem:
        show_problem(problem)
        return
    st.markdown(
        f"**Modèle H2 retenu** : {contribution['model']}. Jeu `{contribution['dataset']}` ; {contribution['folds']}. "
        f"Unité : {contribution['unit']}."
    )
    st.subheader("Chemin de décision (ADR-0048)")
    st.caption("Groupes ajoutés dans l'ordre fixé d'avance, la règle de l'ADR-0037 décidant à chaque étape.")
    st.dataframe(views.contribution_steps_frame(contribution), hide_index=True)
    steps = contribution["steps"]
    st.bar_chart(
        {"Groupe": [f"{x['group']} · {x['label']}" for x in steps], "Gain de log-loss": [x["gain"] for x in steps]},
        x="Groupe", y="Gain de log-loss", y_label="gain de log-loss (nats par match)",
    )  # fmt: skip
    for step in steps:
        st.markdown(f"- **{step['group']} · {step['label']}** : {step['variables']}.")
    st.subheader("Où se concentre le gain de G5")
    st.dataframe(views.contribution_rounds_frame(contribution["g5_by_round"]), hide_index=True)
    st.subheader("Diagnostics, sans pouvoir de décision")
    st.dataframe(views.contribution_other_frame(contribution["diagnostics"]), hide_index=True)
    st.subheader("Structures du modèle (6.8)")
    st.dataframe(views.contribution_other_frame(contribution["structures"], decisions=True), hide_index=True)
    st.subheader("À lire avec ces chiffres")
    st.markdown("\n".join(f"- {note}" for note in contribution["notes"]))
    st.caption(
        f"Rapports : décision `{contribution['reports']['decision']}`, structures `{contribution['reports']['structures']}`."
    )


def model_screen(client: ApiClient) -> None:
    st.header("Modèle")
    st.caption(
        "Modèle actif (live). En rejeu, chaque saison S est prédite par le modèle du pli S, appris sur les "
        "saisons antérieures seulement (ADR-0011) ; sa version figure dans l'écran « Détail »."
    )
    try:
        card = client.active_model()
    except ApiProblem as problem:
        show_problem(problem)
        card = None
    if card:
        st.subheader("Carte d'identité")
        summary = views.card_summary(card)
        st.table({"Rubrique": [r for r, _ in summary], "Valeur": [v for _, v in summary]})
        features = (card.get("model") or {}).get("features") or []
        if features:
            st.markdown("**Variables requises** : " + ", ".join(f"`{f}`" for f in features))
        st.subheader("Validation (4 plis de développement, protocole figé de l'ADR-0037)")
        st.dataframe(views.validation_frame(card), hide_index=True)
        comparisons = views.comparisons_frame(card)
        if not comparisons.empty:
            st.caption("Écart A − B de log-loss du total, apparié, IC 95 % par blocs (A − B > 0 : B est meilleur).")
            st.dataframe(comparisons, hide_index=True)
        limits = views.limits_list(card)
        if limits:
            st.subheader("Limites connues")
            st.markdown("\n".join(f"- {item}" for item in limits))

    st.subheader("Courbe d'apport des groupes de variables")
    if FIGURE.exists():
        st.image(str(FIGURE), caption="Figure générée en partie 4 (docs/resultats/figures/courbe_apport.png).")
    else:
        st.caption("Figure absente de ce dossier.")

    st.subheader("Fraîcheur des données")
    try:
        freshness = client.freshness()
        st.dataframe(
            [{"Source": s["source"], "Dernière mise à jour": s.get("last_update") or "n. d.",
              "Complète jusqu'au": s.get("complete_until") or "n. d.", "Note": s.get("note") or ""}
             for s in freshness["sources"]],
            hide_index=True,
        )  # fmt: skip
        health = client.health()
        st.caption(f"API : {health['status']} ; base : {health['database']} ; modèle chargé : {health.get('model')}")
    except ApiProblem as problem:
        show_problem(problem)


def main() -> None:
    st.set_page_config(page_title="foot-predictor", page_icon="⚽", layout="wide")
    client = ApiClient()
    st.session_state.setdefault("screen", SCREENS[0])
    with st.sidebar:
        st.title("foot-predictor")
        st.radio("Écran", SCREENS, key="screen")
        st.caption(
            "Loi du nombre total de buts d'un match du top 5 : H1 (sans composition), et H2 (avec la composition "
            f"annoncée) en rejeu seulement. Interface locale ; elle ne parle qu'à l'API ({client.base_url})."
        )
    screen = st.session_state.screen
    if screen == "Matchs":
        matches_screen(client)
    elif screen == "Détail":
        detail_screen()
    elif screen == "Apport des variables":
        contribution_screen(client)
    else:
        model_screen(client)


if __name__ == "__main__":
    main()
