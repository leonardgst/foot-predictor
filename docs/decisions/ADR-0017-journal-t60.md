# ADR-0017 — Journal T-60 fait du 9 au 18 octobre 2026, par tâches planifiées

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : ADR-0010 (journal T-60 facultatif, critère de révision de 2 %) ; ADR-0012 (scellé) ; décision d.3 de la session du 2026-09-29 ; `docs/realisation/03_collecte/README.md`, section « Journal T-60 »

## Contexte

L'ADR-0010 garde le journal T-60 comme option facultative avant le gel. C'est le seul moyen de vérifier l'hypothèse de l'évaluation H2 en rejeu : le onze du détail de match est celui annoncé avant le coup d'envoi. Après l'abonnement, les compositions annoncées ne sont plus accessibles.

Faits relevés le 2026-09-29 :

- aucun match du top 5 entre le 21 septembre et le 8 octobre (trêve internationale) ;
- avant le gel, 7 journées du top 5 : 9 (3 matchs), 10 (24), 11 (17), 12 (4), 16 (4), 17 (21) et 18 octobre (19), soit 92 matchs ;
- la documentation v3 annonce les compositions « between 20 and 40 minutes before the fixture ».

## Options envisagées

1. **Les 7 journées** (92 matchs), par tâches planifiées.
2. **Les 4 journées de week-end** (81 matchs).
3. **Pas de journal T-60** : l'hypothèse reste invérifiée, et l'évaluation H2 devra le signaler comme limite.

## Décision

Option 1. Chaque jour :

- une requête pour la liste du jour, avec les heures réelles ;
- à partir de 40 minutes avant chaque coup d'envoi, un lot de 20 matchs toutes les 5 minutes, jusqu'aux compositions ou au coup d'envoi ;
- 80 requêtes au plus par jour (pire cas simulé : 73).

Un seul usage : le bilan `t60-report` à la session de gel, qui compare les titulaires annoncés à ceux du détail d'après-match.

## Conséquences

- 7 tâches planifiées `FootPredictor_t60_<jour>` (ADR-0018). Le portable doit rester allumé, branché et en session ouverte ces jours-là. La commande empêche la mise en veille automatique.
- Les réponses sont rangées sous `api_football/daily/<jour>/`. Elles ne comptent jamais comme « détail reçu » : le planificateur ignore ce dossier, sinon le vrai détail ne serait jamais demandé.
- Le bilan ne lit que les compositions, jamais le score (ADR-0012). Il n'est jamais utilisé pour évaluer un modèle : l'échantillon est trop petit (ADR-0010).
- **Critère de révision** : celui de l'ADR-0010. Plus de 2 % de titulaires différents, ou moins de 50 matchs comparés au gel (échantillon inutilisable) : le signaler comme limite dans l'évaluation H2 (J9).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
