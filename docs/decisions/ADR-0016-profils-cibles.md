# ADR-0016 — Profils ciblés : titulaires sans date de naissance, top 5 puis D2 puis P3

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : ADR-0008 (seconde action avant le gel) ; décision d.1 de la session du 2026-09-29 ; `docs/realisation/03_collecte/README.md`, section « Profils ciblés »

## Contexte

L'ADR-0008 prévoit des requêtes ciblées sur les profils de joueurs « si ce résultat ou les 335 titulaires sans profil le justifient », avec un point d'accès et un coût à vérifier. Le contrôle du brut comptait 1 838 titulaires absents des pages `/players` de leur championnat-saison (335 en P1, 1 503 en P3). Cette mesure ignorait qu'un joueur peut avoir son profil dans une autre saison ou un autre palier.

La documentation v3 donne `/players/profiles?player=<id>` : un profil par requête, avec la date de naissance, sans notion de saison. Une date de naissance ne sera plus accessible après la fin de l'abonnement.

## Options envisagées

1. **P1 seulement** (au plus 335 requêtes) : couvre la population d'évaluation, laisse l'âge inconnu pour les recrues venues de P3.
2. **P1 top 5, puis P1 D2, puis P3**, en ne demandant que les titulaires sans date de naissance dans **aucun** profil du brut. Coût : une requête par joueur.
3. **Rien** : l'âge reste inconnu pour ces joueurs (repli sur la moyenne du poste, ADR-0013).

## Décision

Option 2, dans un plafond de 1 900 requêtes. Titulaires des blocs de championnat qui collectent les profils, dans les saisons de chaque bloc. Identifiants nuls ou égaux à 0 écartés.

## Conséquences

- **Collecte du 2026-09-29** : 925 titulaires sélectionnés (72 top 5, 192 D2, 661 P3) et 927 requêtes. Résultat :
  - 496 dates de naissance obtenues ;
  - 429 titulaires restent sans date (61 top 5, 157 D2, 211 P3). L'API connaît ces joueurs, mais pas leur date de naissance.
- Les profils ciblés sont stockés sous `api_football/player_profiles/`. `raw_check` les lit et compte les titulaires sans date, tous profils confondus.
- Une tâche déjà demandée n'est jamais redemandée : la file dédoublonne les tâches par leur clé.
- **Jalon J3** : le chargeur lit les deux sources de profils (pages `/players` et profils ciblés).
- **Critère de révision** : si l'âge manquant d'une partie des titulaires du top 5 (61, soit moins de 1 %) pèse sur la qualité du XI (J9), chercher une autre source de dates de naissance dans une ADR dédiée.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
