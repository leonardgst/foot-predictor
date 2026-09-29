# ADR-0020 — Collisions d'identifiants : exclusion automatique au chargement, numéro de la composition pour « deux numéros dans la même équipe »

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : remplace l'ADR-0015 (proposée) ; ADR-0008 (règle 3 et critère de révision) ; décision d.1 de la session « partie 2 » du 2026-09-29 ; `docs/realisation/05_controle_qualite/constats_collisions.md`, section « Impact sur le top 5 »

## Contexte

L'ADR-0015 proposait d'exclure automatiquement, au chargement, les entrées de joueurs en collision (un identifiant API, deux personnes), avec un YAML réservé aux exceptions. Elle posait deux critères de révision : plus de 1 % des matchs du top 5 touchés, ou une collision sur un joueur à fort temps de jeu dans le top 5.

Mesures du 2026-09-29, sur P1 à P3 (même règle que `raw_check`), championnats du top 5 seulement :

| Mesure | Valeur |
|---|---|
| Matchs de championnat du top 5 touchés par au moins une entrée en collision | **46 sur 29 170 (0,16 %)** ; 43 sur 27 164 avant le 1er juillet 2025 |
| Par championnat | Serie A 24, Liga 9, Premier League 6, Ligue 1 4, Bundesliga 3 |
| Par type (matchs du top 5) | même jour 41 ; deux numéros dans la même équipe 5 ; deux équipes dans le même match 0 ; deux naissances 0 |
| Titularisations du top 5 que l'exclusion enlèverait | 34, dans 34 matchs |
| Identifiants en collision avec au moins 20 titularisations dans une saison du top 5 | **9** (13 au seuil de 10) |
| Titularisations du top 5 de ces 9 identifiants, et part exclue | 808, dont 31 exclues (3,8 %) |
| Joueur-saisons du top 5 (au moins 10 titularisations) qui perdraient plus de 10 % de leurs titularisations | 4 (de 11 % à 25 %) |
| « Deux numéros dans la même équipe » (tous paliers) | 297 cas, dont **189 résolus sans ambiguïté** par le numéro de maillot de la composition |
| Avec cette résolution (option 2b) : matchs du top 5 touchés, titularisations exclues | 42 matchs, 30 titularisations, **toutes du type « même jour »** ; les 4 joueur-saisons au-dessus de 10 % restent |

Le premier critère n'est pas atteint. Le second l'est : 9 joueurs à fort temps de jeu sont touchés. Pour la plupart, la perte est faible ; 4 joueur-saisons perdent toutefois de 11 à 25 % de leurs titularisations. Tous ces cas sont des collisions « même jour » : un joueur du top 5 et un homonyme d'un autre championnat, le même jour.

Dans le cas « deux numéros dans la même équipe », la composition porte l'identifiant avec un seul numéro, et les statistiques en portent deux : celle au numéro de la composition est la bonne, l'autre appartient à un coéquipier. La preuve est dans le brut.

## Options envisagées

1. **ADR-0008 telle quelle** : un YAML écrit à la main, cas par cas. Long à écrire et à relire, et une scission exige de savoir qui est qui.
2. **Exclusion automatique au chargement** (ADR-0015) : toute entrée en collision devient « joueur inconnu », qui compte 0.
3. **2b** : comme 2, mais pour « deux numéros dans la même équipe », on garde l'entrée dont le numéro est celui de la composition et on n'exclut que l'autre.
4. **Changer de clé de joueur** : contraire au constat que l'identifiant est fiable à 99,9 %.

## Décision

Option **2b**.

- Le chargeur applique la même détection que `raw_check`, grâce à une **fonction partagée et testée** (`ingestion/collisions.py`). `raw_check` l'appellera après le gel (règles du gel, partie 2).
- **Deux numéros dans la même équipe** : si la composition porte l'identifiant avec un seul numéro, et qu'une seule entrée de statistiques a ce numéro, cette entrée est gardée et les autres sont exclues. Sinon (identifiant deux fois dans la composition, ou absent), toutes les entrées sont exclues.
- **Autres types** (même jour, deux équipes dans le même match, deux naissances) : les entrées en cause sont chargées comme joueur inconnu (ADR-0008, règle 1). Pour « deux naissances », aucune date de naissance n'est retenue pour cet identifiant.
- **Pas de scission manuelle pour l'instant** des joueurs à fort temps de jeu. L'exclusion leur enlève 27 titularisations sur 808, mais 4 joueur-saisons en perdent plus de 10 %. Les compositions ne servent qu'à l'horizon H2 (ADR-0010), au jalon J9 : aucune variable du MVP n'en dépend. La seule preuve disponible pour ces cas « même jour » est l'équipe (un identifiant, deux clubs de championnats différents). Une scission par équipe sera étudiée au J9, dans une nouvelle ADR, si l'expérience « qualité du XI » y est sensible.
- Le YAML `ingestion/mappings/player_collisions.yaml` ne porte que les exceptions (scission prouvée, faux positif à rétablir). Il est vide au départ.

Les règles 1, 2 et 4 de l'ADR-0008 sont inchangées.

## Conséquences

- **Jalon J3 (partie 2)** :
  - module `ingestion/collisions.py`, testé sur des cas synthétiques (un cas positif et un cas négatif par type, faux positifs, résolution par le numéro) ;
  - le chargeur traite l'identifiant 0 comme absent et prend l'équipe d'un joueur dans la composition ;
  - `check-referentiel` compte les entrées exclues par match et par championnat-saison, et recalcule les deux critères de révision.
- **Ce que l'on s'interdit** : écrire une scission sans preuve dans le brut (numéro, équipe, date de naissance).
- **Doublons** (97 groupes) : inchangés, YAML d'alias de l'ADR-0008.
- **Critères de révision** :
  - plus de 1 % des matchs de championnat du top 5 touchés (aujourd'hui 0,14 % avec 2b) ;
  - au J9, une variable H2 sensible aux titularisations exclues. Aujourd'hui, 4 joueur-saisons du top 5 perdent plus de 10 % de leurs titularisations (au plus 25 %).
  Dans ces deux cas, étudier une scission prouvée par l'équipe, dans une nouvelle ADR.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
