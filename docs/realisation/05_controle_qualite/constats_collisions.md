# Constats du test de collision des identifiants de joueurs — P1 à P3 (2026-09-29)

Lecture du résumé `reports/data_quality/raw_check_P1-P2-P3_2026-09-29.md` (section 5) et de son fichier de détails (local, non versionné). Les trois paliers sont contrôlés **ensemble**, pour voir aussi les cas qui réunissent deux paliers. Ce document ne cite que des nombres et des libellés de championnat-saison, aucun nom ni identifiant de joueur.

**Scellé (ADR-0012).** Le test porte sur les identifiants (compositions, statistiques joueurs, profils), jamais sur les scores ni les buts.

## Ce qui est cherché (ADR-0008, règle 3)

Une **collision** est un identifiant API qui désigne deux personnes. Elle se repère au comportement, pas au nom :

| Type | Règle | Source |
|---|---|---|
| Même jour | un identifiant chez deux équipes différentes le même jour (UTC) | compositions et statistiques de tous les matchs détaillés |
| Même match | un identifiant deux fois dans un match : chez les deux équipes, ou avec deux numéros de maillot dans la même équipe | idem |
| Deux naissances | un identifiant avec deux dates de naissance dans les profils `/players` | profils de P1 et P3 |

Une date de naissance qui change **une fois** d'une saison à l'autre (date A jusqu'à une saison, date B ensuite) est une correction de l'API : elle est classée à part, pas en collision.

## Résultats bruts, puis après tri des faux positifs

| Type | Premier passage (règle brute) | Après tri | Faux positifs écartés |
|---|---|---|---|
| Même jour | 27 identifiants, 319 cas | **26 identifiants, 143 cas** | identifiant 0 |
| Même match | 1 186 identifiants, 1 869 cas | **62 identifiants, 313 cas** (13 chez les deux équipes, 49 avec deux numéros dans la même équipe) | 1 292 cas « statistiques inversées » (31 matchs), 43 cas « entrée répétée » (24 matchs), identifiant 0 |
| Deux naissances | 3 identifiants | **3 identifiants** | — |
| Naissance corrigée (à part) | 3 | 3 | — |
| **Total, tous types** | — | **81 identifiants distincts** | — |

Présences examinées : 3 995 826 (joueur, match), sur 102 089 matchs.

### Causes des faux positifs

1. **Identifiant 0.** L'API donne l'identifiant `0` à des joueurs qu'elle ne connaît pas (1 680 entrées). Ce n'est pas un joueur : il apparaissait chez les deux équipes d'un même match et dans des dizaines de matchs le même jour. Il est écarté des collisions. **Point pour J3** : le contrôle « player.id présent partout » ne compte que les identifiants absents (`null`), pas l'identifiant 0. Le chargeur devra traiter les deux comme « inconnu » (ADR-0008, règle 1).
2. **Statistiques rattachées à l'équipe adverse.** Dans 31 matchs, tous les joueurs (28 à 52 par match) ont leur composition dans une équipe et leurs statistiques dans l'autre : c'est le bloc `players` qui porte le mauvais `team.id`. La règle : à partir de 5 joueurs dans ce cas dans un même match, c'est le match qui est en cause, pas les identifiants. Pour le contrôle « même jour », la composition fait foi. Ces 31 matchs sont surtout en 2025 (MLS, Argentine, Ligue Europa Conférence, Coppa Italia). **Point pour J3** : l'équipe d'un joueur se lit dans la composition, pas dans les statistiques.
3. **Entrée répétée.** 43 cas dans 24 matchs : la même entrée (même équipe, même numéro) répétée dans les statistiques, jusqu'à une vingtaine de fois. Même personne : pas une collision.

### Ce que sont les 81 collisions restantes

L'examen des listes détaillées (local) montre de **vraies collisions**, de trois sortes :

- **homonymes de championnats différents** (surtout lusophones et hispanophones), rattachés au même identifiant. Exemple type : un joueur du top 5 et un homonyme en MLS ou au Brésil, qui jouent le même jour ;
- **frères ou jumeaux d'un même club**, partageant un identifiant : deux numéros de maillot dans la même équipe, le même jour ;
- **statistiques d'un coéquipier portant l'identifiant d'un autre** : un titulaire et une seconde entrée de statistiques à un autre numéro, répétées sur plusieurs matchs.

Aucun faux positif n'a été relevé parmi les cas examinés. Le seuil de 5 joueurs pour les « statistiques inversées » laisse 8 matchs avec 1 ou 2 cas isolés : ils sont comptés comme collisions (homonymes dans le même match).

## Par palier

Identifiants distincts ; un identifiant peut compter dans plusieurs colonnes. « P1+P3 » : cas qui réunit deux paliers, invisible dans un contrôle palier par palier.

| Paliers | Même jour | Même match, deux équipes | Même match, deux numéros | Deux naissances | Naissance corrigée | Doublons (groupes) | dont inter-paliers |
|---|---|---|---|---|---|---|---|
| P1 | 9 | 4 | 30 | 0 | 2 | 32 | 0 |
| P3 | 15 | 9 | 21 | 3 | 0 | 55 | 0 |
| P1+P3 | 6 | 0 | 0 | 0 | 1 | 7 | 0 |

- P2 (compositions seules avant 2015, sans profils) n'a aucune collision propre.
- **Top 5** (population d'évaluation, ADR-0012) : la collision « même match » touche 3 identifiants et 5 matchs. Toutes collisions confondues, 576 matchs sur 102 089 (0,6 %) contiennent au moins un identifiant en collision.

## Doublons entre paliers

94 groupes de doublons probables (même nom, même date de naissance, deux identifiants) sur 46 811 profils, soit la somme exacte des contrôles par palier (33 en P1, 61 en P3). 7 groupes ont des profils dans les deux paliers, mais chacun a au moins deux identifiants dans un même palier : **aucun doublon n'apparaît seulement grâce au contrôle commun**. Le YAML d'alias (ADR-0008) portera donc sur 94 groupes.

**Mise à jour après les profils ciblés (même jour, ADR-0016)** : 97 groupes de doublons sur 47 377 profils, dont toujours aucun seulement inter-paliers. Les collisions sont inchangées (81 identifiants).

## Comparaison au critère de révision de l'ADR-0008

L'ADR-0008 prévoit de revoir la règle 3 au-delà de « quelques dizaines de collisions réelles (seuil indicatif : 50) ». **Avec 81 identifiants, le seuil est dépassé.** En proportion, l'identifiant API reste très fiable : 81 identifiants sur 70 569 joueurs vus (0,11 %).

Conformément à la règle des ADR, l'ADR-0008 n'est pas modifiée : l'[ADR-0015](../../decisions/ADR-0015-collisions-traitement-automatique.md) (statut « proposée ») présente les options et une recommandation. Elle est à trancher avant le jalon J3, au plus tard au début de la partie 2.

## Coût du test

Le test n'ajoute **aucune passe** sur le brut : les présences sont relevées pendant la lecture des détails et des profils déjà faite par `raw_check`, puis regroupées une fois, à la fin, avec numpy (environ 4 millions de présences, 5 colonnes d'entiers de 8 octets, soit 160 Mo).

| Mesure (P1 à P3 ensemble) | Avant | Après |
|---|---|---|
| Contrôle, rendus compris, dans le même processus et dans les mêmes conditions | 82 s | 90 s (+ 10 %) |
| Commande complète (`time`), selon la charge du portable | 84 à 266 s | 131 à 199 s |

Les durées de la commande complète varient du simple au triple d'un lancement à l'autre sur ce portable : seule la mesure dans les mêmes conditions est comparable.
