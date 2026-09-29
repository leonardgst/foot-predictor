# ADR-0023 — Sources externes : football-data retenu, Understat écarté (xG d'API-FOOTBALL seulement)

- **Statut** : acceptée
- **Date** : 2026-09-29
- **Référence** : rapport de cadrage, A.4 (critère juridique), G.12, décision M17 ; décision d.5 de la session « partie 2 » du 2026-09-29 ; ADR-0003, ADR-0011 (live), ADR-0012 (scellé), ADR-0013 (xG dans le MVP)

## Contexte

Le rapport (M17) demande de vérifier les conditions d'utilisation et le `robots.txt` d'Understat, avec le critère appliqué à Transfermarkt (A.4 : n'utiliser que des sources dont les conditions le permettent), avant d'en dépendre. Understat est la seule source gratuite d'xG historique pour le top 5 ; l'ADR-0013 compte sur l'xG (groupe G2) dans le MVP.

**Faits relevés le 2026-09-29** :

| Source | Constat |
|---|---|
| Understat, `robots.txt` | `User-agent: *` puis `Disallow: /` : tout accès automatisé est refusé, pour tous les agents. Aucune autre page n'a été lue ensuite, pour respecter ce refus. |
| football-data, `data.php` | « its use is intended for private individuals only, NOT commerical or data training products using automated bots/scrapers/AI » ; « made available for the purposes of league match prediction only ». |
| football-data, `robots.txt` | `User-agent: *` sans restriction ; seuls des robots d'IA et d'aspiration massive sont bloqués (GPTBot, ClaudeBot, CCBot…). |
| API-FOOTBALL, `expected_goals` dans les statistiques d'équipe (championnats du top 5, brut) | absent de 2010-11 à 2021-22 ; environ la moitié des matchs en 2022-23 ; 99 à 100 % en 2023-24 et 2024-25 ; présent en 2025-26 et 2026-27 (présence seulement, scellé). |

## Options envisagées

1. **(a)** xG Understat pour l'apprentissage et le rejeu, sans Understat en live.
2. **(b)** xG Understat aussi en live.
3. **(c)** Pas de collecte Understat : xG d'API-FOOTBALL là où il existe, sinon buts seuls.

## Décision

**Option (c)**, par la règle fixée à l'étape 0 : (a) si les conditions permettent l'accès automatisé, (c) si elles l'interdisent ou restent floues. Le `robots.txt` d'Understat l'interdit.

- Aucune requête vers Understat, ni collecteur Understat. Les anciennes lignes `raw.understat_*` de l'ancienne base dev ne sont pas reprises dans le référentiel.
- L'xG disponible est celui d'API-FOOTBALL (statistiques d'équipe, chargé dans `staging` quand il est présent).
- **football-data est retenu.** Le projet est l'usage que le site décrit : un particulier, la prédiction de matchs de championnat, sans usage commercial ni produit d'entraînement d'IA. Le téléchargement reste poli : 270 fichiers une fois, une requête par seconde au plus, `User-Agent` qui identifie le projet, aucune recollecte inutile. Ce point d'interprétation est à relire par l'utilisateur (retour de la partie 2).

## Conséquences

- **MVP (partie 3).** Sans xG avant 2022-23, le groupe G2 (xG) de l'ADR-0013 ne peut pas porter sur la période d'apprentissage 2015-16 à 2021-22. Son usage (période réduite, indicateur de présence, ou abandon au profit des tirs) sera tranché dans une ADR de la partie 3, sur des mesures.
- **Code** : `ingestion/understat*.py`, `mapping_builder/collect_understat_teams.py`, le YAML `understat_teams.yaml` et la dépendance `understatapi` sont retirés avec l'ancien code (partie 2, sous-étape 2.8).
- **Live** (ADR-0011) : sans xG Understat, comme la règle 4 de l'ADR-0011 le prévoyait déjà.
- **Critère de révision** : Understat publie des conditions qui autorisent l'accès automatisé, ou une autre source d'xG historique, gratuite et légale, apparaît. Nouvelle ADR dans ce cas.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
