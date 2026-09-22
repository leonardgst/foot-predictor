# Récap : backfill 10 saisons et bug de persistance du xG (22/09/2026)

Suite directe de `recap_mise_en_ordre_git_et_verifications.md`. Cette session exécute le prérequis B du guide `API_FOOTBALL_ABONNEMENT.md` (ingérer les saisons plus anciennes avant de payer l'abonnement API-Football), et découvre au passage un vrai bug de persistance du xG, présent depuis la mise en place initiale du pipeline.

---

## 1. Objectif

La base de dev ne contenait que la saison 2024-2025 (1 752 matchs). `api_football.py` ignore tout match absent de `staging.match`, donc un futur backfill API-Football sur plusieurs saisons échouerait silencieusement sans ce travail préalable. Le guide d'abonnement (section 4, prérequis B) demandait d'ingérer football-data.co.uk **et** Understat pour les saisons manquantes avant de payer.

## 2. Ce qui a été exécuté (lecture-écriture sur la base de dev, avec accord explicite)

| # | Script | Modification | Résultat |
|---|---|---|---|
| 1 | `football_data_scraper.py` | Aucune (déjà en boucle sur 10 saisons) | 18 011 lignes créées en `raw.football_data_match`, 0 erreur |
| 2 | `football_data.py` | Aucune | 18 011 lignes traitées → `staging.match` / `team_match` |
| 3 | `understat_scraper.py` | **Modifié** : bouclait sur une seule saison (2024) en dur, étendu à `range(2015, 2025)` sur le modèle de `football_data_scraper.py` | ~50 appels Understat (léger, 1 appel par championnat/saison), 0 erreur |
| 4 | `understat.py` | **Bug corrigé** (voir section 3) | 17 970 → 18 008 lignes de xG résolues après corrections, 3 ignorées |

**Volumes finaux de `staging.match` par compétition** (matchs joués, 2015-08 à 2025-05) :

| Compétition | Matchs |
|---|---|
| Premier League | 3 800 |
| La Liga | 3 800 |
| Serie A | 3 800 |
| Bundesliga | 3 060 |
| Ligue 1 | 3 551 |

`staging.team` contient 160 équipes, `check_duplicates.py` confirme **0 doublon**.

## 3. Deux anomalies trouvées et corrigées

### 3.1 Ajaccio GFCO / AC Ajaccio (mapping d'équipe)

**Symptôme** : 41 lignes de xG ignorées sur les 18 011, toutes liées à un seul club.

**Cause** : deux clubs corses distincts existent dans la fenêtre 2015-2025 — le vrai **GFC Ajaccio** (Gazélec, seule saison en Ligue 1 : 2015-2016) et le vrai **AC Ajaccio** (promu en 2022-2023). football-data.co.uk les distingue correctement par des libellés différents (`Ajaccio GFCO` pour 2015-2016, `Ajaccio` pour 2022-2023), mais **les deux YAML** (`football_data_teams.yaml` et `understat_teams.yaml`) mappaient le libellé `Ajaccio` vers le canonique `GFC Ajaccio` — une erreur d'étiquette qui touchait en réalité le club AC Ajaccio. Comme les deux sources partageaient la même erreur, aucun plantage cross-source ne s'est produit pour 2022-2023. Le vrai problème venait de `Ajaccio GFCO` (2015-2016), absent des deux YAML : `get_or_create_team` retombait sur le nom brut comme identité, créant une équipe orpheline (id 145) distincte de celle qu'Understat retrouvait par nom (`GFC Ajaccio`, id 178 — qui contenait en réalité les matchs d'AC Ajaccio 2022-2023).

**Correctif appliqué** :
1. Renommage en base : équipe id 178 `GFC Ajaccio` → `AC Ajaccio` ; équipe id 145 `Ajaccio GFCO` → `GFC Ajaccio`.
2. YAML corrigés : `Ajaccio: AC Ajaccio` (au lieu de `GFC Ajaccio`) dans les deux fichiers ; ajout de `Ajaccio GFCO: GFC Ajaccio` dans `football_data_teams.yaml`.
3. **Correction du `TeamSourceMapping` déjà enregistré** : le renommage seul n'a pas suffi — `get_or_create_team` retrouve d'abord le mapping `(source_name, source_ref)` déjà enregistré, sans reconsulter le YAML ni le nom (leçon n°1 du RECAP, vérifiée une fois de plus). La ligne `TeamSourceMapping(source_name='understat', source_ref='GFC Ajaccio')`, qui pointait vers l'id 178, a dû être repointée manuellement vers l'id 145.

**Aucune donnée n'a été mélangée entre les deux clubs** : ils étaient déjà correctement séparés en base, seul le nom affiché était inversé. Une fois corrigé : 41 → 3 lignes ignorées (les 3 restantes sont des décalages de date sans lien avec Ajaccio, voir section 3.3).

### 3.2 Bug de persistance du xG dans `understat.py` (découverte principale)

**Symptôme** : après le premier correctif Ajaccio, une vérification de la couverture de `staging.team_match.xg_for` a montré seulement **2 368 lignes sur 36 022** (6,6 %) avec un xG renseigné — alors que le script annonçait 18 008 lignes « traitées » sans erreur.

**Cause** : la fonction `upsert_team_match_xg` (dans `common.py`), qui écrit réellement `xg_for` / `xg_against` sur une ligne `team_match` existante, était **importée dans `understat.py` mais jamais appelée**. La boucle de `ingest_understat_match_stats` résolvait le match via `resolve_match_cross_source`, incrémentait le compteur `processed`, puis passait directement à la ligne suivante — sans jamais écrire les valeurs de xG lues depuis `raw.understat_match_stats`. Le compteur de succès ne mesurait donc que la résolution du match, pas la persistance des données.

**Impact réel** : ce bug touchait aussi la saison 2024-2025, déjà présentée comme validée dans `RECAP_PROJET.md` (section 7, « 1752 lignes de xG équipe traitées, 0 ignorée »). Ce chiffre était vrai pour la résolution, mais **le xG n'a jamais été réellement stocké** avant ce correctif — y compris lors des runs précédant cette session. Les 2 368 lignes déjà présentes avant le fix proviennent probablement d'un état antérieur de la base ou d'un test partiel, non de ce pipeline dans son état pré-correctif.

**Correctif appliqué** : ajout des deux appels `upsert_team_match_xg` (un pour chaque équipe du match, avec `xg_for`/`xg_against` inversés selon le côté) dans la branche de succès de la boucle, juste avant `processed += 1`.

**Résultat après correctif et ré-exécution** : couverture de `xg_for` passée de **6,6 % à 99,98 %** (36 016 / 36 022 lignes `team_match`).

### 3.3 Résidu : 3 matchs non résolus

| Match | Compétition |
|---|---|
| Caen - Toulouse (2018-04-14) | Ligue 1 |
| Strasbourg - Lyon (2023-04-30) | Ligue 1 |
| Udinese - Roma (2024-04-14) | Serie A |

Les dates diffèrent entre Understat et football-data de plus d'un jour (hors tolérance ±1 jour de `resolve_match_cross_source`, documentée en section 9.3 du RECAP). Probablement de vrais matchs reportés (calendrier chargé, coupe d'Europe). Volume négligeable (0,017 % des lignes), non creusé davantage.

## 4. État des prérequis du guide d'abonnement

| Prérequis | Statut |
|---|---|
| A — `api_football_competitions.yaml` | ✅ Fait (session précédente) |
| B — Ingérer les saisons plus anciennes (football-data + Understat) | ✅ Fait (cette session) |
| C — Choisir le nombre de saisons | ✅ 10 saisons (valeur par défaut), déjà en base |

**Les 3 prérequis techniques sont maintenant cochés.** Il ne reste que la décision de payer, qui dépend de ta disponibilité (~3 jours pour relancer le script au fil du quota).

## 5. Fichiers modifiés, non commités au moment de la rédaction

- `src/foot_predictor/ingestion/understat_scraper.py` — boucle sur 10 saisons au lieu d'une
- `src/foot_predictor/ingestion/understat.py` — **correctif du bug de persistance du xG**
- `src/foot_predictor/ingestion/mappings/football_data_teams.yaml` — mapping Ajaccio / AC Ajaccio
- `src/foot_predictor/ingestion/mappings/understat_teams.yaml` — idem

Les renommages d'équipes et la correction du `TeamSourceMapping` ne vivent que dans la base de dev (pas de fichier à commiter pour ça) : ils devront être reproduits manuellement sur test et prod le jour où ce backfill y sera répliqué, exactement comme les 19 fusions de la section 9.3 du RECAP.

## 6. Points de vigilance pour la suite

- **Le bug de persistance du xG aurait pu passer inaperçu longtemps** : le compteur de succès du script ne reflétait pas la réalité de ce qui était écrit en base. Ça renforce l'intérêt de vérifier des colonnes précises après une ingestion, pas seulement le compte de lignes « traitées ».
- **Reproduire la correction Ajaccio sur test et prod** avant d'y lancer le même backfill, sinon le même bug (41 lignes ignorées) s'y reproduira à l'identique.
- Le pipeline `market_value/` reste bloqué par l'abonnement API-Football (voir `RECAP_PROJET.md` section 11 et `API_FOOTBALL_ABONNEMENT.md`), indépendamment de ce backfill.
