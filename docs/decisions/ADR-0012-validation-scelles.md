# ADR-0012 — Validation glissante sur 2021-22 à 2024-25 ; matchs postérieurs au 30 juin 2025 sous scellés

- **Statut** : acceptée
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, B.4 (M3), C.2, I.5, I.6, I.7, I.8, décision M11 ; ADR-0009 (population d'évaluation renvoyée ici), ADR-0010, ADR-0011

## Contexte

- **Le test actuel n'est plus vierge.** Le protocole actuel repose sur une seule saison de test (2024-25, environ 1 700 matchs). Cette saison a déjà servi à choisir entre les modèles A et B et à écarter la recalibration (rapport B.4, M3).
- **Un test d'une saison est trop petit.** Détecter un gain de l'ordre de 0,002 de log-loss par match demande plusieurs milliers de matchs de test (rapport C.2).
- **La saison 2025-26 est déjà dans le brut** depuis le palier P1 (2026-09-27), mais pas encore dans `staging`. Le début de la saison 2026-27 (août à octobre 2026) l'est aussi. Le scellé ne peut donc plus reposer sur l'absence des données : il doit être une **règle protégée par le code**.
- **Deux versions devront être testées** : le MVP, horizon H1 (jalon J6, vers janvier 2027), et la version intermédiaire, horizon H2 (vers mi-2027 ; ADR-0010). Aucune autre saison vierge avec compositions ne sera disponible : la saison 2026-27 n'en aura plus après le gel (ADR-0011).
- **Population d'évaluation.** Des D2, des coupes et 11 autres championnats sont collectés (ADR-0002). Le produit vise les championnats du top 5 ; l'ADR-0009 renvoie ici le choix de la population d'évaluation.
- **Régimes particuliers** à traiter dans tous les plis : matchs à huis clos (fin 2019-20 et 2020-21), Ligue 1 à 18 clubs depuis 2023-24.

## Options envisagées

1. **Une seule saison de test** (actuel) : trop petite, déjà utilisée pour décider.
2. **Validation glissante sur 2021-22 à 2024-25, saison 2025-26 sous scellés, saison 2026-27 en prospectif.**

Pour l'usage de la saison scellée :

- **a.** Strictement une seule fois : la version intermédiaire n'aurait pas de test final.
- **b.** Une fois par version : le second usage ne mesure que l'écart entre H2 et le modèle H1 déjà figé.

## Décision

Option 2, avec la variante b.

1. **Période de développement : matchs antérieurs au 1er juillet 2025.**
   - L'apprentissage commence en 2015-16.
   - Les saisons 2010 à 2014 (et football-data avant, si besoin) servent seulement à amorcer l'Elo et les fenêtres glissantes.
2. **Validation glissante.**
   - 4 plis à fenêtre croissante : on apprend sur toutes les saisons antérieures et on teste sur 2021-22, 2022-23, 2023-24, puis 2024-25, soit environ 7 000 matchs de test.
   - Hyperparamètres choisis par validation interne sur la dernière saison d'apprentissage de chaque pli.
   - Imputation et standardisation ajustées dans le pli.
   - Écarts de perte appariés match par match, intervalle à 95 % par bootstrap par blocs de journées.
3. **Population d'évaluation : matchs de championnat du top 5**, avec les exclusions de l'ADR-0009.
   - Les données d'apprentissage (top 5 seul, avec les D2, ou tous les championnats collectés) sont un **choix expérimental**, jugé sur cette même population.
   - Les coupes servent aux variables (calendrier, compositions), jamais à l'évaluation.
4. **Scellé : tout match joué à partir du 1er juillet 2025**, donc la saison 2025-26 et le début de 2026-27.
   - Aucune exploration, aucun réglage, aucune évaluation sur ces matchs pendant le développement.
   - Seule exception : leur usage comme historique pour calculer des variables à l'inférence, une fois le modèle figé.
   - **Scellé technique.** La construction du jeu de données d'apprentissage et la commande d'évaluation refusent ces matchs, sauf avec une option explicite `--sealed-test`. Chaque usage de cette option ajoute une ligne à un journal versionné : date, commit, fichier d'expérience, résultat.
   - Les notebooks d'exploration respectent la même frontière.
   - Le rejeu de l'application suit la règle 2 de l'ADR-0011.
5. **Test scellé : une fois par version.**
   - Avant chaque test, la liste des modèles comparés est figée : fichier d'expérience commité et tag Git.
   - Le test est lancé une seule fois, et le résultat est publié tel quel dans `docs/`, même décevant.
   - Aucun modèle n'est modifié ensuite pour améliorer ce résultat.
   - **MVP (H1)** : modèle retenu, références B0 et B1, référence de marché.
   - **Version intermédiaire (H2)** : le second usage mesure **uniquement** l'écart entre H2 et le modèle H1 déjà figé.
   - Après le test, le modèle retenu est réentraîné sur toutes les données disponibles pour le live.
6. **Prospectif.** Les prédictions live de 2026-27, journalisées avant le coup d'envoi (ADR-0011), forment le dernier niveau de preuve.

## Conséquences

- **Code.**
  - `modeling/split.py` est complété : plis glissants, validation interne, frontière du scellé.
  - La construction du jeu de données et `fp evaluate` implémentent le refus et l'option `--sealed-test`.
  - Un test vérifie qu'aucun match postérieur au 30 juin 2025 n'entre dans un pli sans l'option.
- **Nouveau fichier versionné.** Un journal des tests scellés, par exemple `reports/sealed_tests.md` (nom indicatif).
- **Le jalon J6** (rapport L) contient le test scellé du MVP ; le jalon J9 contient celui de la version intermédiaire.
- **Les résultats antérieurs** (log-loss de 2,933 sur 2024-25) restent un repère historique, pas une référence de sélection.
- **Critères de révision.**
  - Si l'intervalle de confiance des écarts sur 4 plis reste trop large pour trancher les questions principales (G1 et G2 contre la référence B1), ajouter un pli (2020-21), en traitant explicitement le huis clos.
  - Si le scellé est levé par erreur (usage hors journal), le constater dans une nouvelle ADR et réduire la portée de la conclusion du test concerné.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
