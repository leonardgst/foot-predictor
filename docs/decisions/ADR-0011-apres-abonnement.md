# ADR-0011 — Après l'abonnement : rejeu en mode principal, live partiel « avant composition »

- **Statut** : acceptée
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, C.3, C.6, E.1, F.5, F.6, G.11, I.3, I.8, décision M10 ; ADR-0005, ADR-0008 (complétée sur un point), ADR-0010

## Contexte

Après le 2026-10-22 (ADR-0005), l'offre gratuite d'API-FOOTBALL se limite aux saisons 2022 à 2024 : plus de calendrier, de résultats ni de compositions pour la saison en cours. Les sources gratuites restantes :

| Source | Apporte | Limites |
|---|---|---|
| football-data | Résultats et prochains matchs (avec cotes) du top 5 et des D2 | Mise à jour environ deux fois par semaine ; **pas de coupes** |
| Understat | xG du top 5 | Statut juridique à vérifier (décision M17) |
| Brut API figé au 19 octobre | Calendrier 2026-27 avec identifiants API (3 618 matchs « NS » à la fin de P1) | **Dates figées**, souvent fausses ensuite (programmation TV, reports) ; calendrier des coupes vite épuisé |

Conséquences directes :

- **Appariement.** La règle de l'ADR-0008 (domicile, extérieur, date à ±1 jour) échouera pour les matchs postérieurs au gel, dont la date API sera périmée.
- **Variable « jours de repos » (G3).** Elle dépend des coupes et ne sera plus alimentée en live.
- **Fraîcheur.** Avant un match de milieu de semaine, football-data peut ne pas encore contenir les résultats du week-end.
- **Saison scellée.** Si la saison 2025-26 est mise sous scellés (décision M11), un rejeu ouvert sur cette saison ferait voir les résultats du test avant l'heure.

## Options envisagées

1. **Live seulement** : dépend entièrement des sources gratuites, sans composition ; fragile.
2. **Rejeu seulement** : toujours démontrable et évaluation visible, mais aucun vrai prochain match.
3. **Les deux** : rejeu en mode principal, live « avant composition » (H1, ADR-0010) partiel, à partir de sources gratuites.

## Décision

Option 3, avec six règles.

1. **Le rejeu est le mode principal.** L'utilisateur choisit une date de référence. Les variables sont calculées avec la même fonction qu'à l'entraînement, à partir des matchs antérieurs au jour du match (ADR-0010). Limite documentée : les valeurs sont celles collectées en septembre-octobre 2026, éventuellement révisées depuis (xG recalculés, scores corrigés ; rapport I.8).
2. **Saisons ouvertes au rejeu.** Jusqu'au test final sur la saison scellée, le rejeu ne s'ouvre que sur les saisons antérieures à celle-ci (jusqu'à 2024-25 si M11 scelle 2025-26). Il s'étend ensuite à toutes les saisons.
3. **Live H1.**
   - Calendrier : la liste API figée, pour les identifiants, complétée par le fichier des prochains matchs de football-data, pour les dates réelles et les cotes.
   - Résultats : football-data.
   - **Complément à l'ADR-0008.** Pour les matchs de championnat postérieurs au gel, l'appariement football-data ↔ API se fait par (compétition, saison, équipe à domicile, équipe à l'extérieur). Cette clé est unique dans une saison de championnat ; la date n'y intervient pas.
4. **Un modèle ne peut être actif dans un mode que si toutes ses variables y sont disponibles.**
   - Si le modèle retenu utilise une variable indisponible en live (G3, par exemple), le live utilise le meilleur modèle qui s'en passe. Les deux sont de toute façon évalués dans la courbe d'ablation.
   - Si la variable n'apporte pas de gain significatif, un seul modèle sert aux deux modes.
5. **Une variable est « périmée »** quand sa source ne contient pas encore tous les matchs antérieurs au jour du match. La prédiction est alors indisponible, avec la raison et la date de la dernière mise à jour de la source.
6. **Journalisation.** Chaque prédiction live est écrite dans `ops.prediction` **avant le coup d'envoi**, avec l'horizon et la version du modèle : c'est l'évaluation prospective de 2026-27.

**Hors périmètre de cette ADR** : la présence de l'xG d'Understat en live, qui dépend de la décision M17.

## Conséquences

- **Collecteur football-data.** Un court collecteur (prochains matchs et résultats, fichiers tels que téléchargés, ADR-0003) est ajouté aux jalons J7-J8. Il vient s'ajouter au chargement historique de football-data.
- **Rien de plus à faire avant le gel** que le `refresh` du 19 octobre déjà prévu (ADR-0005).
- **Application.**
  - Choix du mode (rejeu ou live), avec les saisons de rejeu limitées selon la règle 2.
  - Statut par variable : présente, manquante ou périmée, avec raison.
  - Mention du modèle actif dans chaque mode.
  - En rejeu, affichage du score réel.
- **API.** La route `GET /matches` prend `mode=live|replay` (rapport F.6) et refuse une saison de rejeu non ouverte.
- **Critère de révision.** Si, sur les premières semaines de live, plus d'un match sur cinq du top 5 est indisponible pour cause de données périmées, revoir la source des résultats ou la règle de fraîcheur (seuil indicatif).

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
