# ADR-0013 — Pas de masse salariale ; « qualité du XI » en version intermédiaire ; MVS gelé

- **Statut** : acceptée
- **Date** : 2026-09-28
- **Référence** : rapport de cadrage, B.4 (M6, I10), C.3, E.1, E.2, G.12, I.3 (G1, G5), décisions M12 et M29 ; `docs/realisation/05_controle_qualite/constats_P1_P2.md` ; ADR-0008, ADR-0010, ADR-0011, ADR-0012

## Contexte

Le projet veut mesurer l'apport de la « masse salariale » ou de la valeur du onze. Aucune source n'est à la fois disponible, légale et datée match par match :

| Piste | Problème |
|---|---|
| Masse salariale réelle (estimations publiques) | Payante ou obtenue par scraping, incomplète, non datée match par match |
| Estimation d'un salaire (club, âge, poste) | Hypothèses arbitraires, invérifiables |
| Valeur marchande (Transfermarkt et jeux dérivés) | Fragile juridiquement (CGU, droit des bases de données), déjà écartée dans le dépôt |
| MVS maison (`market_value/`, environ 1 700 lignes avec les tests) | Pondérations fixées à la main ; composante « réputation » fonction du classement ; aucune vérité terrain pour le valider |

Constats de la collecte (P1 et P2) :

- **Statistiques joueurs** (notes, minutes, postes) : présentes dans 95,9 % des matchs de P1, et seulement 0,8 % de P2. Les indicateurs fondés sur les joueurs ne sont calculables qu'**à partir de 2015-16**.
- **Anomalies** : 1 154 notes vides ou hors de la plage 3 à 10 (entrées en fin de match), 22 minutes hors de 0 à 130.
- **Âge** : 335 titulaires n'ont pas de profil ; ils sont couverts par l'action avant le gel de l'ADR-0008.
- **Notes entre championnats.** Les notes API ne sont pas comparables d'un championnat à l'autre. Or le palier P3 apporte le passé de joueurs recrutés hors du top 5 et des D2.
- **Horizon.** La qualité du XI dépend de la composition : elle relève de l'horizon H2 (ADR-0010) et ne fonctionne pas en live après l'abonnement (ADR-0011).
- **`hdbscan`.** La dépendance ne sert qu'au MVS. Dans `market_value/clustering/build_clusters.py`, son import est protégé et un repli sur un mélange gaussien existe. Le test qui l'utilise est ignoré si le paquet est absent (`pytest.importorskip`).

## Options envisagées

1. **Poursuivre le MVS** : lourd et invérifiable.
2. **Mettre le MVS en pause** : force de l'équipe mesurée par l'Elo dès le MVP, indicateur « qualité du XI » en version intermédiaire.
3. **Supprimer le MVS** : perte d'un exercice non supervisé possible, sans gain.

## Décision

Option 2.

1. **Écartés définitivement** : masse salariale réelle, estimation de salaire, valeur marchande et jeux qui en dérivent (confirme la décision M29).
2. **MVP.** La force de l'équipe est portée par l'**Elo** (groupe G1) et l'**xG** (groupe G2), sans autre substitut de la masse salariale.
3. **Version intermédiaire, horizon H2 : groupe G5 « qualité du XI ».** Au plus **3 variables par équipe** dans la première expérience :
   - **Qualité moyenne des titulaires.** Pour chaque titulaire, note API sur ses matchs **strictement antérieurs**, pondérée par les minutes et **rapprochée de la moyenne de son poste** (estimation bayésienne empirique). Un joueur sans historique reçoit la moyenne de son poste. Variante à comparer : contributions par 90 minutes au lieu de la note.
   - **Part des titulaires habituels absents.**
   - **Âge moyen des titulaires.**
4. **Données et nettoyage.**
   - Période : à partir de 2015-16.
   - Les notes vides ou hors plage sont ignorées, les minutes aberrantes écartées.
   - Le poste vient des statistiques joueurs.
   - Au départ, une recrue venue d'un championnat hors du périmètre d'apprentissage reçoit la moyenne de son poste. La **règle de comparaison des notes entre championnats** est définie au jalon J9, dans l'expérience G5.
5. **Règle de repli.** Si l'intervalle à 95 % du gain de log-loss du total au-delà de l'Elo et de l'xG contient 0 (protocole de l'ADR-0012), le groupe G5 est abandonné, et ce résultat négatif est publié dans `docs/`.
6. **MVS gelé.**
   - Code et tests conservés, sans évolution.
   - Hors du MVP et de la version intermédiaire.
   - Possible exercice non supervisé en version avancée (rapport E.3).

## Conséquences

- **PR de nettoyage** (celle qui retire les anciens collecteurs, ADR-0004 et ADR-0007) :
  - retrait de `hdbscan` de `pyproject.toml`, sans effet sur le code ni sur les tests ;
  - mention « gelé (ADR-0013) » en tête de `market_value/__init__.py`.
- **Registre des variables.** Il distingue G1 (MVP, H1) de G5 (H2). Les tables `features.player_market_value_score` et `features.player_style_profile` restent en place, sans être alimentées.
- **Documentation.** Le README ne présente plus le MVS (agrégat « z11 », composantes restantes) comme une prochaine étape du modèle. Cette mise à jour se fait lors de la restructuration de la documentation (décision M19).
- **Critères de révision.**
  - Si une source légale et datée de masse salariale devient disponible gratuitement, rouvrir la question dans une nouvelle ADR.
  - Si la note API se révèle trop lacunaire sur certaines saisons ou certains championnats (plus de 10 % de titulaires sans note hors fin de match, seuil indicatif), basculer sur la variante « contributions par 90 minutes ».

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
