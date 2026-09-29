# ADR-0015 — Collisions d'identifiants de joueurs : traitement automatique au chargement

- **Statut** : proposée (à trancher avant le jalon J3)
- **Date** : 2026-09-29
- **Référence** : ADR-0008 (règle 3 et critère de révision) ; `docs/realisation/05_controle_qualite/constats_collisions.md` ; résumé `reports/data_quality/raw_check_P1-P2-P3_2026-09-29.md`

## Contexte

L'ADR-0008 traite chaque collision (un identifiant API, deux personnes) par un YAML versionné, « scindée ou exclue » au cas par cas. Elle prévoit de revoir la règle 3 au-delà de « quelques dizaines de collisions réelles (seuil indicatif : 50) ».

Le test de collision, lancé sur P1 à P3 ensemble le 2026-09-29, trouve après tri des faux positifs :

| Constat | Valeur |
|---|---|
| Identifiants en collision réelle | **81** sur 70 569 joueurs vus (0,11 %) |
| Matchs contenant au moins un identifiant en collision | 576 sur 102 089 (0,6 %) |
| Top 5, collision « même match » | 3 identifiants, 5 matchs |
| Faux positifs écartés automatiquement | identifiant 0 (1 680 entrées), statistiques rattachées à l'équipe adverse (31 matchs), entrées répétées (24 matchs) |

Le seuil est dépassé, mais pas pour la raison que le critère redoutait. L'identifiant API reste fiable à 99,9 %. Le problème est pratique : 81 cas, dont certains répétés sur des dizaines de matchs, font un YAML long à écrire et à relire à la main. Or le test sait déjà désigner **le match et l'entrée** en cause.

## Options envisagées

1. **Garder l'ADR-0008 telle quelle** : un YAML écrit à la main, cas par cas (scission en deux personnes, ou exclusion). Conséquences : environ 81 entrées, plusieurs heures de relecture au jalon J3 ; la scission exige de savoir qui est qui, ce que le brut ne dit pas toujours.
2. **Exclusion automatique au chargement, YAML pour les exceptions.** Le chargeur applique la même détection que `raw_check`, grâce à une fonction partagée. Dans un match, une entrée en collision est chargée comme **joueur inconnu**, qui compte 0 (ADR-0008, règle 1). Le YAML ne sert plus qu'aux exceptions : une scission voulue à la main, ou un faux positif à rétablir. Conséquences : reproductible, testé ; 576 matchs perdent une ou deux entrées ; aucune personne n'est inventée.
3. **Changer de clé de joueur** (identifiant API plus groupe de noms). Conséquences : complexe, et contraire au constat que l'identifiant est fiable à 99,9 % ; les homonymes resteraient ambigus.

## Décision

Proposée : **option 2**. Le chargeur exclut automatiquement les entrées en collision, avec la même règle que `raw_check`, et le YAML ne porte que les exceptions. Les règles 1, 2 et 4 de l'ADR-0008 sont inchangées.

## Conséquences

- **Jalon J3.**
  - La détection des collisions sort de `quality/raw_check.py` vers une fonction partagée, testée, que le chargeur et le contrôle appellent.
  - Le chargeur traite l'identifiant 0 comme un identifiant absent, et prend l'équipe d'un joueur dans la composition, pas dans les statistiques.
  - Un contrôle J3 compte les entrées exclues par match et par championnat-saison.
- **Ce que l'on s'interdit** : écrire une scission sans preuve dans le brut (numéro, équipe, date de naissance).
- **Doublons** (94 groupes, aucun seulement inter-paliers) : inchangés, YAML d'alias de l'ADR-0008.
- **Critère de révision** : plus de 1 % des matchs du top 5 touchés, ou une collision découverte sur un joueur à fort temps de jeu dans le top 5. L'exclusion enlèverait alors un titulaire important à de nombreux matchs : il faudrait une scission manuelle.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
