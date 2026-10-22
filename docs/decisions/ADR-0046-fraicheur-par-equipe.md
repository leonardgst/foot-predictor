# ADR-0046 — Live : fraîcheur par équipe, approchée, au lieu de par championnat

- **Statut** : acceptée
- **Date** : 2026-10-22
- **Référence** : ADR-0011 (règle 5, et son critère de révision), ADR-0031 (Elo), ADR-0032 (glissants), ADR-0040 (même fonction), ADR-0042 (fraîcheur par championnat, critère de révision) ; E-062 ; `reports/inference/live_2026-10-22.md`

## Contexte

- **Règle actuelle** (ADR-0011, règle 5 ; ADR-0042) : un match du jour J n'est prédit que si **tous** les matchs d'avant J de **son championnat** ont un résultat. Sinon, ses variables d'historique sont « périmées » et aucune prédiction n'est faite.
- **Premier live réel, le 2026-10-22** : 56 matchs du top 5 sur 7 jours, 5 disponibles, **91 % indisponibles**. Football-data ne publie les résultats qu'environ deux fois par semaine, si bien que seuls les matchs du lendemain d'une mise à jour passent. Le critère de révision de l'ADR-0011 (plus d'un match du top 5 sur cinq) est atteint dès le premier jour. L'ADR-0042 citait déjà la piste d'une fraîcheur par équipe.
- **Ce que lisent les variables du modèle** (ADR-0031, ADR-0032) : les matchs **joués et non exclus** des 10 championnats des échelles nationales ; les coupes n'entrent dans aucune variable, et les variables de contexte (G0) n'ont pas d'historique.
  - **Elo (G1)** : il dépend des matchs passés de l'équipe et de la note de ses adversaires au moment de chacun d'eux.
  - **Moyennes glissantes (G2)** : elles dépendent des matchs de l'équipe, mais sont tirées vers un **a priori μ**, la moyenne de **tout le championnat** sur les 730 jours avant J, avec un poids k = 3.
- **Conséquence** : soit C le dernier jour où le championnat est complet. Si ni A ni B n'a de match de championnat entre C et J (bornes exclues), l'Elo des deux équipes à J est **identique** à celui de l'historique complet. Leurs glissants sont **approchés** : μ ne contient pas les résultats des autres matchs du championnat joués entre C et J. Un premier brouillon de cette ADR les disait exacts ; les tests l'ont démenti avant toute fusion.
- **Mesure de l'approximation** (2023-24, période de développement, modèle du pli 2023-24). Sur 107 jours de week-end, 1 455 matchs du top 5, on simule une collecte le jeudi précédent : les résultats des matchs des 10 championnats entre jeudi et J sont retirés.

  | | Fraîcheur par championnat | Fraîcheur par équipe |
  |---|---|---|
  | Matchs prévisibles dès le jeudi | 1 sur 1 455 | 1 455 sur 1 455 |
  | Écart maximal d'une variable G2 | 0 | 0,0009 (buts), 0,0005 (`xg_proxy`) |
  | Écart maximal de λ | 0 | 0,0011 (médiane des maxima par jour : 0,0003) |
  | Écart maximal de P(T > 2,5) | 0 | 0,0004 (médiane : 0,0001) |

  Pour situer ces chiffres : au test scellé, l'écart moyen de calibration de P(T > 2,5) est de 0,025.

## Options envisagées

1. **Fraîcheur par équipe, approchée.**
   - Un match A–B du jour J n'est périmé que si A ou B a un match de championnat entre C et J, quel que soit son statut sauf annulé.
   - Presque tous les matchs du week-end deviennent prévisibles dès la mise à jour du milieu de semaine.
   - L'Elo reste exact ; G2 est approché, de l'ordre de 10⁻³ au plus sur λ.
   - En contrepartie, la règle « même fonction » (ADR-0040) n'est plus tenue au bit près pour G2.
2. **Fraîcheur par championnat, exacte.** Aucune approximation, mais seuls les matchs du lendemain d'une mise à jour sont prévisibles, et le journal prospectif reste très mince. Aucune variante par équipe n'est exacte, puisque μ dépend de tout le championnat.
3. **Prédire malgré des résultats manquants de l'équipe elle-même.** L'écart serait cette fois de l'ordre d'un match entier : contraire à l'ADR-0040 et à la règle « aucune valeur de remplacement ». Écartée.

## Décision

Option 1, choisie par l'utilisateur le 2026-10-22 après la mesure ci-dessus.

- **Règle** : pour un match A–B du jour J, soit C la date de complétude de son championnat (ADR-0042, inchangée). Les variables d'historique sont périmées si et seulement si **C < J − 1 et** A ou B a un match d'un des 10 championnats des échelles daté strictement entre C et J, quel que soit son statut sauf annulé : joué, à jouer ou reporté. Un résultat connu ne lève pas le blocage, car on ne vérifie pas l'historique de son adversaire de proche en proche.
- **Tolérance**, fixée avant la vérification, environ 5 fois le maximum mesuré : |Δλ| ≤ **0,005** et |ΔP(T > 2,5)| ≤ **0,002** entre une prédiction faite avec la règle par équipe et la même prédiction faite avec l'historique complété. **L'Elo doit être identique**, sans tolérance.
- **Transparence** : chaque réponse garde `data_complete_until`, la date de complétude de son championnat. Une date antérieure à J − 1 signale une prédiction faite avec la règle par équipe. Quand le match reste périmé, la raison nomme les équipes qui ont un match dans l'intervalle, avec ses dates.
- **Vérification** :
  - tests unitaires sur données synthétiques : Elo identique, G2 proche mais non identique, verdict de tolérance ;
  - répétition du live (`check --only live`, gel simulé au 2024-02-15, « aujourd'hui » simulé le 2024-03-09). Pour les **sept jours suivants**, les matchs déclarés disponibles sont comparés à la même superposition complétée de leurs résultats manquants (mêmes fichiers, donc mêmes tirs). Avec le modèle du pli de la saison, l'Elo doit être identique, et λ et P(T > 2,5) doivent rester dans la tolérance.
- **Ce qui ne change pas** : la date de complétude par championnat (`/data/freshness`, rapport live), la superposition de football-data, le rejeu (toujours à jour, donc exact), E-062 (une réponse live indisponible n'est jamais écrite).

## Conséquences

- Fichiers :
  - `inference/availability.py` : `teams_busy_between` et la garde ;
  - `inference/predict.py` : application ;
  - `inference/check.py` : répétition sur sept jours, tolérances ;
  - tests et README de l'étape 11.
- **L'ADR-0040 est assouplie sur un point**. En live, les variables G2 d'un match prédit avec la règle par équipe sont approchées, dans la tolérance ci-dessus. Partout ailleurs, la règle « même fonction » reste exacte : rejeu, live quand le championnat est complet, contrôles de lignes.
- **L'évaluation prospective** (ADR-0011, règle 6) porte sur ces prédictions telles qu'écrites. L'approximation y est incluse et documentée, et sa taille est négligeable devant l'incertitude du modèle.
- La règle 5 de l'ADR-0011 est **précisée** : sont pris en compte les matchs qui entrent dans les variables du match, selon la règle ci-dessus. La fraîcheur par championnat de l'ADR-0042 est remplacée sur ce point (statut mis à jour).
- **Critères de révision** :
  - un Elo différent, ou un écart de λ ou de P(T > 2,5) hors tolérance, dans la répétition ou dans une vérification a posteriori du live ;
  - une part d'indisponibles encore au-delà d'un sur cinq sur les premières semaines.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
