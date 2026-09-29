# ADR-0019 — Palier P4 : classements du top 5 et des D2, indisponibilités des titulaires du top 5

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : ADR-0002 (P4 « selon le reste ») ; décisions d.2 et d.4 de la session du 2026-09-29 ; `docs/realisation/03_collecte/README.md`, section « Palier P4 et listes isolées »

## Contexte

L'ADR-0002 laisse le contenu de P4 à définir : `/sidelined`, classements officiels, journal quotidien. P1 à P3 sont collectés et contrôlés.

- **Classements** : le quota le permet sans peine, mais aucune variable du MVP n'en dépend ; ils se recalculent à partir des matchs.
- **`/sidelined`** : l'historique des blessures et des suspensions d'un joueur. Il complète `/injuries`, que l'API ne couvre qu'à partir de 2021 environ. La documentation v3 accepte 20 joueurs par requête.
- **MLS 2017** : un match semble manquer à la liste (constats P3, catégorie c).

## Options envisagées

1. **Pas de P4** : aucune dépense, mais pas d'historique de blessures avant 2021, ni de classements officiels (pénalités de points, départages).
2. **Classements du top 5 et des D2** (saisons terminées 2010-2025, 146 requêtes) et **`/sidelined` des titulaires du top 5** 2015-2026 (396 lots de 20) ; plus une nouvelle demande de la liste MLS 2017 (2 requêtes au plus).
3. **L'option 2, étendue à P3** : environ 130 classements et plusieurs milliers de joueurs de plus, pour des championnats hors de la population d'évaluation.

## Décision

Option 2. `sidelined` passe par la commande `plan-sidelined`, pas par le YAML : les lots de 20 restent figés d'un `run` à l'autre.

## Conséquences

- **Collecte du 2026-09-29** :
  - 146 classements ;
  - 396 lots `sidelined`, soit 7 915 titulaires ;
  - 2 requêtes pour la MLS 2017. La nouvelle liste est **identique** : l'API ne connaît pas le match manquant. C'est un trou de la source, documenté dans `constats_P3.md` et `DATA_FREEZE.md`.
- Les classements de la saison en cours ne sont pas collectés : ils seraient périmés au gel.
- Les indisponibilités ne sont utilisables que pour les titulaires du top 5. Une recrue venue d'un autre championnat n'a d'historique que si elle a déjà été titulaire dans le top 5.
- **Jalon J4** : décider si `/sidelined` alimente une variable de disponibilité (groupe G3), et comment dater chaque indisponibilité par rapport au match (horizon H1, ADR-0010).
- **Critère de révision** : si une variable issue de `/sidelined` n'apporte rien en validation (J5-J6), ne plus s'en servir. Les données restent dans le brut.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
