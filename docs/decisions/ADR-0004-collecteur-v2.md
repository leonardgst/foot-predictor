# ADR-0004 — Réécrire le collecteur API-FOOTBALL avant de poursuivre la collecte

- **Statut** : acceptée
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, B.4 (D4, D5, D6), G.6, G.8, décision M4

## Contexte

Le collecteur actuel fait un appel par match, ignore le champ `errors` de l'API et les en-têtes de quota, vérifie les doublons en parcourant tout le JSONB, et ne stocke le brut que dans Postgres. Le périmètre retenu (ADR-0002) le rend inadapté.

## Options envisagées

1. Garder le collecteur actuel : aucun développement, mais collecte lente, fragile et silencieusement incomplète en cas d'erreur de plan ou de paramètre.
2. **Un collecteur v2** développé sur une branche courte (environ 5 h de travail, relecture comprise).

## Décision

Option 2, sur la branche `fix/03-collecteur-lots-ids`. Exigences minimales :

- `/fixtures?ids=` par lots de 20 ;
- lecture systématique du champ `errors` et des en-têtes `x-ratelimit-requests-remaining` et `X-RateLimit-Remaining` ;
- au plus 2 requêtes par seconde ; pause de 60 s sur une réponse 429 ; 3 tentatives avec attente croissante sur une erreur 5xx ou un délai dépassé ;
- arrêt propre sous une réserve de quota configurable (500 par défaut) ;
- stockage selon ADR-0003 ; file de travail reprenable (`pending`, `done`, `failed`, `suspect`) dans un fichier SQLite, pour que la collecte ne dépende pas de Docker ;
- collecte indépendante de Postgres : le collecteur n'écrit que dans `data/raw/` ;
- commande de suivi : quota du jour, files, échecs, progression par palier ;
- tests unitaires sur 3 à 5 payloads réels anonymisés, **sans aucun appel réseau** ;
- aucune requête réelle lancée par Claude Code sans accord explicite.

## Conséquences

- Environ une journée de décalage avant la reprise de la collecte, compensée par un coût divisé par environ 20.
- L'ancien `api_football_scraper.py` et `injuries_scraper.py` restent en place, marqués « obsolètes », jusqu'à la PR de nettoyage.
- Le code de chargement vers staging n'est **pas** concerné par cette ADR : il sera refait après la collecte (décision M7).
