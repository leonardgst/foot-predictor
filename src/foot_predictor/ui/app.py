"""Interface Streamlit : trois écrans au-dessus de l'API locale (rapport F.7, ADR-0040).

Lancement (l'API doit tourner) :

    uv run python -m foot_predictor.api serve          # terminal 1
    uv run streamlit run src/foot_predictor/ui/app.py  # terminal 2, puis http://127.0.0.1:8501

| Écran | Contenu | Routes appelées |
|---|---|---|
| Matchs | mode, date, championnats ; pastille de disponibilité et raisons ; bouton « Prédiction » | `/competitions`, `/matches` |
| Détail | loi du total (barres), E[T], λ, intervalle et couverture annoncée, P(T > 2,5), variables, score réel | `POST /matches/{id}/predictions`, `/matches/{id}/availability` |
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

SCREENS = ("Matchs", "Détail", "Modèle")
MODES = {"Rejeu": "replay", "Live": "live"}
DEFAULT_REPLAY_DATE = dt.date(2025, 5, 18)  # journée de 2024-25, saison de rejeu ouverte en phase A
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


def open_detail(client: ApiClient, match: dict, mode: str, predict: bool) -> None:
    """Rappel d'un bouton : appelle l'API, garde la réponse ou l'erreur, puis passe à l'écran « Détail »."""
    state = st.session_state
    try:
        if predict:
            state.detail = client.predict(match["match_id"], mode)
        else:
            state.detail = client.availability(match["match_id"], mode)
        state.detail_error = None
    except ApiProblem as problem:
        state.detail, state.detail_error = None, problem
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
        help="Rejeu : matchs passés, prédits avec le modèle du pli de leur saison (2021-22 à 2024-25 en phase A). "
        "Live : matchs à venir, modèle actif ; ouvert après le test scellé (phase B).",
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


def detail_screen() -> None:
    state = st.session_state
    st.header("Détail")
    problem: ApiProblem | None = state.get("detail_error")
    answer: dict | None = state.get("detail")
    if problem is not None:
        match = state.get("detail_match") or {}
        if match:
            st.subheader(f"{match.get('home_team')} – {match.get('away_team')}")
        show_problem(problem)
        return
    if not answer:
        st.info("Choisir un match dans l'écran « Matchs » (bouton « Prédiction » ou « Variables »).")
        return

    st.subheader(f"{answer.get('home_team')} – {answer.get('away_team')}")
    mode = "rejeu" if answer["mode"] == "replay" else "live"
    st.caption(
        f"{answer.get('competition')} · {answer['date']} · {views.kickoff_label(answer)} · "
        f"saison {answer['season']}-{str(answer['season'] + 1)[-2:]} · mode {mode} · horizon {answer['horizon']}"
    )
    st.markdown(f"Disponibilité : {views.badge(answer['status'])}" + (
        f" — {views.reasons_text(answer)}" if answer.get("reasons") else ""))  # fmt: skip

    prediction = answer.get("prediction")
    if prediction:
        cols = st.columns(4)
        cols[0].metric("E[T] (buts attendus)", views.number(prediction["expected_total"]))
        cols[1].metric("λ domicile", views.number(prediction["lambda_home"]))
        cols[2].metric("λ extérieur", views.number(prediction["lambda_away"]))
        cols[3].metric("P(T > 2,5)", views.percent(prediction["p_over_2_5"]))
        st.markdown(f"**Intervalle [q10 ; q90]** : {views.interval_text(prediction)}")
        st.bar_chart(
            views.distribution_frame(prediction), x="Buts", y="Probabilité", color="Intervalle", sort=False,
            x_label="nombre total de buts T", y_label="P(T = k)",
        )  # fmt: skip
        actual = views.actual_score_text(answer)
        if actual:
            st.info(f"Score réel (rejeu) : {actual}")
        market = answer.get("market_reference")
        if market:
            st.caption(
                f"Référence de marché (cotes avant clôture, jamais une variable du modèle, ADR-0036) : "
                f"P(T > 2,5) implicite = {views.percent(market['p_over_2_5'])}"
            )
    elif answer["status"] == "available":
        st.info("Toutes les variables sont présentes : le bouton « Prédiction » de l'écran « Matchs » calcule la loi.")

    st.subheader("Variables utilisées et manquantes")
    variables = answer.get("variables") or []
    if variables:
        missing = sum(v["status"] != "presente" for v in variables)
        st.caption(f"{len(variables) - missing} présentes, {missing} manquantes ou périmées (aucune valeur remplacée).")
        st.dataframe(views.variables_frame(variables), hide_index=True)
    else:
        st.caption("Aucune variable évaluée pour ce match (hors périmètre, exclu ou H2).")

    saved = answer.get("saved")
    lines = [
        f"Modèle : `{answer['model_version']}`",
        f"Version des données : `{answer['data_version']}` ; données complètes jusqu'au {answer['data_complete_until']}",
    ]
    if saved:
        origin = "créée maintenant" if saved.get("created") else "déjà tracée, renvoyée telle quelle"
        lines.append(f"Prédiction n° {saved.get('id')} de `ops.prediction` ({origin}, {saved.get('created_at')})")
    st.caption("  \n".join(lines))


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
            "Loi du nombre total de buts d'un match du top 5, horizon H1 (sans composition). "
            f"Interface locale ; elle ne parle qu'à l'API ({client.base_url})."
        )
    screen = st.session_state.screen
    if screen == "Matchs":
        matches_screen(client)
    elif screen == "Détail":
        detail_screen()
    else:
        model_screen(client)


if __name__ == "__main__":
    main()
