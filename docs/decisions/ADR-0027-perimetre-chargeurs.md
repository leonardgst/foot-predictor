# ADR-0027 — Périmètre des chargeurs du référentiel (jalon J3)

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : ADR-0008 (référentiel), ADR-0009 (cible), ADR-0013 (MVP et H2), ADR-0016 (profils), ADR-0019 (P4), ADR-0023 (sources) ; décision d.6 de la session « partie 2 » du 2026-09-29

## Contexte

Le brut API-FOOTBALL contient bien plus que ce dont le MVP (horizon H1) et la version intermédiaire (horizon H2) ont besoin : transferts, classements, indisponibilités (`sidelined`), blessures, carrière des entraîneurs. Chaque chargeur coûte du code, des tests et du temps de chargement. Le brut reste de toute façon disponible et sauvegardé (ADR-0006).

## Options envisagées

1. **Tout charger** dès J3 : plus long, sans usage avant les parties 4 à 6.
2. **Charger ce qu'utilisent le MVP et H2**, reporter le reste.

## Décision

Option 2. `load` (partie 2) charge :

- compétitions, saisons, équipes et matchs : statut, coup d'envoi UTC, score au temps réglementaire distinct du score final, exclusions de l'ADR-0009 ;
- compositions (titulaires, remplaçants, numéro, poste, grille), entraîneur et formation de chaque équipe ;
- statistiques joueurs et statistiques d'équipe (dont l'xG API quand il existe) ;
- profils : pages `/players` et profils ciblés (date de naissance, nationalité, nom) ;
- football-data : appariement aux matchs API, et matchs hors couverture API (ADR-0008, règle 2).

**Reportés** : transferts, classements (`standings`), `sidelined`, `injuries`, cotes football-data (elles restent dans le CSV brut), carrière des entraîneurs (`coachs`). Aucune variable du MVP ni de l'horizon H2 ne les utilise (ADR-0013). Leurs chargeurs viendront en partie 4 ou 6, sans nouvelle collecte.

Non chargés, par règle : `api_football/daily/` (compositions d'avant-match du journal T-60, E-025) et les champs illisibles de façon fiable (`passes.accuracy`, tantôt un nombre, tantôt un pourcentage).

## Conséquences

- Tables en place mais vides après `load` : `staging.player_injury`, `staging.player_source_mapping`, `staging.coach_source_mapping`.
- La référence de marché (cotes football-data, rapport I.6) se chargera avec les références du protocole (partie 4).
- **Critère de révision** : une variable retenue dans le registre des variables (partie 3) qui a besoin d'une donnée reportée.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
