# API-Football : quand payer, comment faire, comment me le dire

Guide de décision pour l'abonnement API-Football, qui est le point bloquant du projet (voir `RECAP_PROJET.md`, section 11).

> ⚠️ **Tarifs non vérifiés.** Les chiffres de quota et de prix ci-dessous viennent du commentaire de `api_football_scraper.py` (Pro : 7 500 requêtes/jour, 19 €/mois ; gratuit : 100 requêtes/jour, historique limité aux ~2 derniers jours). La page officielle des tarifs était inaccessible lors de la rédaction. **Vérifie le prix et le quota sur le site avant de payer.**

---

## 1. Ce que l'abonnement débloque

Sans lui, ces éléments restent vides ou impossibles à calculer :

- `staging.lineup` et `staging.player_match_stats` (aujourd'hui vides) ;
- `squad_avg_age` et `squad_stability_score_season` ;
- tout le module `market_value/` (clustering, MVS), qui n'a jamais tourné sur de vraies données.

État actuel de la base de dev : **1 752 matchs, tous de la saison 2024-2025** (Premier League 380, La Liga 380, Serie A 380, Bundesliga 306, Ligue 1 306), et `raw.api_football_fixture_detail` contient **0 ligne**.

## 2. Combien de requêtes faut-il ?

Le scraper utilise `/fixtures?id=`, soit **1 requête par match terminé**, plus 1 requête par couple (championnat, saison) pour lister les matchs.

| Périmètre | Requêtes | Durée (1 s entre deux appels) | Jours de quota Pro (7 500/jour) |
|---|---|---|---|
| 1 saison (2024-2025) | ≈ 1 757 (1 752 + 5) | ≈ 30 min | moins de 1 jour |
| 10 saisons (2015-2016 à 2024-2025, valeur par défaut du script) | ≈ 18 200 | ≈ 2 h par jour | 3 jours |

Les 10 saisons sont une estimation : Ligue 1 est passée de 20 à 18 clubs en 2023, et certains matchs peuvent manquer. Le script est **idempotent et reprenable** : relancé le lendemain, il saute les matchs déjà en base (`_fixture_already_ingested`) sans consommer de quota.

**Conséquence pratique** : le plan gratuit (100/jour et historique limité) ne convient pas au backfill. Le plan payant n'est nécessaire que pour **quelques jours** : un mois d'abonnement suffit largement, puis tu peux le résilier.

## 3. Quand payer

**Ne paie pas avant que tous les prérequis de la section 4 soient cochés.** L'abonnement se paie au mois : autant qu'il serve à 100 % du temps.

Tu peux payer dès que :

1. le fichier de mapping des championnats existe (prérequis A) ;
2. les matchs des saisons voulues sont déjà en `staging.match` (prérequis B) ;
3. tu as choisi le nombre de saisons (prérequis C) ;
4. tu es disponible ~3 jours pour relancer le script chaque jour.

## 4. Prérequis à faire AVANT de payer

**A. ✅ Fait le 2026-09-22.** `src/foot_predictor/ingestion/mappings/api_football_competitions.yaml` existe et contient les 5 identifiants, confirmés via un vrai appel à l'endpoint `/leagues` (plan gratuit, 1 seule requête, aucune donnée de match consommée) :

```yaml
E0:  {api_football_league_id: 39}    # Premier League, England
SP1: {api_football_league_id: 140}   # La Liga, Spain
D1:  {api_football_league_id: 78}    # Bundesliga, Germany
I1:  {api_football_league_id: 135}   # Serie A, Italy
F1:  {api_football_league_id: 61}    # Ligue 1, France
```

Bonus constaté lors de l'appel : les 5 championnats couvrent les compositions (`coverage.fixtures.lineups`) pour les saisons 2024, 2025 et 2026 côté API-Football.

**B. Ingérer les saisons plus anciennes côté football-data (et Understat) d'abord.**
`api_football.py` ne crée jamais de match : si le match n'existe pas déjà en `staging.match`, la ligne est **ignorée** (`match is None` → `skipped`). Or la base ne contient que 2024-2025. Télécharger 10 saisons chez API-Football sans avoir les 9 autres en staging donnerait des données brutes inexploitables. Le `__main__` de `football_data_scraper.py` prévoit déjà `range(2015, 2025)`.

**C. Choisir le nombre de saisons.** Tu peux garder les 10 saisons par défaut : le coût de l'abonnement ne change pas (3 jours de quota dans tous les cas). Le vrai coût d'une saison en plus est du temps et de la taille de base. À titre de repère, le MVS utilise une fenêtre de 50 matchs par joueur, soit environ 1,3 saison.

**D. Contrôles sans risque avec le plan gratuit :**
- `APP_ENV=dev PYTHONIOENCODING=utf-8 uv run python check_env.py` (sans l'encodage, l'affichage des emojis plante sous la console Windows) ;
- vérifier que `api_football_teams.yaml` couvre bien les 96 équipes canoniques (voir la leçon n°1 du RECAP : un mapping corrigé après coup ne répare pas les entités déjà créées).

## 5. Comment faire une fois abonné

1. **S'abonner** sur le site d'API-Football (plan payant avec quota ≥ 7 500/jour et historique complet), puis copier la clé.
2. **Fournir la clé** via la variable d'environnement `API_FOOTBALL_KEY`. Elle est lue par `os.environ` : **elle n'est pas lue dans les fichiers `.env.*`**. Dans un terminal bash :
   ```bash
   export API_FOOTBALL_KEY="ta_clé"
   ```
   Ne la colle jamais dans un fichier versionné, ni dans une conversation.
3. **Lancer le téléchargement** (jour 1) :
   ```bash
   APP_ENV=dev uv run python -m foot_predictor.ingestion.api_football_scraper
   ```
   Le quota étant plafonné à 7 500/jour, le script s'arrêtera en erreur en cours de route : c'est attendu. **Relance-le le lendemain** (le quota est remis à zéro à 00:00 UTC) et ainsi de suite jusqu'à ce qu'il n'y ait plus que des `already_ingested`.
4. **Ingérer en staging** (après le téléchargement) :
   ```bash
   APP_ENV=dev uv run python -m foot_predictor.ingestion.api_football
   ```
5. **Compléter avec Understat par joueur** : `understat_player_scraper.py` puis `understat_player.py` (xG / xA / npxG par joueur).
6. **Vérifier** : nombre de lignes de `staging.lineup` et `staging.player_match_stats`, et taux de lignes ignorées (le RECAP a déjà montré qu'un taux élevé cache un vrai problème de mapping).
7. **Résilier l'abonnement** une fois le backfill terminé, sauf si tu veux ensuite des mises à jour régulières. Les mises à jour quotidiennes (quelques dizaines de matchs) tiennent dans le quota gratuit : à vérifier au moment voulu.

## 6. Comment me le dire plus tard

Je ne garde pas la mémoire d'une conversation à l'autre. Pour reprendre au bon endroit, ouvre une nouvelle conversation dans ce projet et écris quelque chose comme :

> « J'ai pris l'abonnement API-Football (plan X, quota Y/jour). Lis `docs/API_FOOTBALL_ABONNEMENT.md` et `docs/RECAP_PROJET.md`, vérifie les prérequis de la section 4, puis lance le backfill. »

Ce message suffit : je relis ces documents, je vérifie l'état de la base (ce que j'ai fait pendant cette session) et je continue. Précise aussi :
- **le nombre de saisons voulu** (10 par défaut) ;
- **si la clé est déjà définie** dans ton terminal (`API_FOOTBALL_KEY`). Ne me la donne pas : dis-moi seulement qu'elle est en place.

Si tu me demandes de lancer le scraper moi-même, je le ferai seulement après ton feu vert explicite, puisqu'il consomme du quota payant.

## 7. Récapitulatif

| Question | Réponse |
|---|---|
| Quand payer ? | Quand les prérequis A, B et C sont faits, et que tu peux relancer le script 3 jours de suite |
| Combien de temps l'abonnement ? | 1 mois suffit (backfill ≈ 3 jours pour 10 saisons) |
| Blocage indépendant du paiement | ~~`api_football_competitions.yaml` manque~~ réglé le 2026-09-22 |
| Piège à éviter | Télécharger des saisons absentes de `staging.match` : les lignes seraient ignorées |
| Où mettre la clé ? | Variable d'environnement `API_FOOTBALL_KEY`, pas de fichier `.env` |
| Comment reprendre avec moi ? | Message de la section 6 dans une nouvelle conversation |
