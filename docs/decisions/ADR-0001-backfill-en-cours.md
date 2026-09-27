# ADR-0001 — Sort du backfill API-FOOTBALL en cours

- **Statut** : acceptée
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, B.4 (D4 à D8), G.2, décision M1

## Contexte

Un backfill a été lancé le 2026-09-22 avec `ingestion/api_football_scraper.py` : un appel `/fixtures?id=` par match, brut stocké uniquement dans `raw.api_football_fixture_detail` (volume Docker).

Préférence exprimée : **un seul export et une seule sauvegarde, une fois toute la collecte terminée**, plutôt que des exports au fil de l'eau.

Fait déterminant : tant que l'abonnement est actif (jusqu'au 2026-10-22, ADR-0005), toute donnée perdue se recollecte pour presque rien. Recollecter les ~18 000 matchs du backfill par lots de 20 coûte **moins de 1 000 requêtes**, sur un quota restant de plus de 100 000.

## Options envisagées

1. Laisser le script finir, puis exporter son contenu JSONB vers des fichiers.
2. L'arrêter, exporter le JSONB, et faire lire cet export par le collecteur v2 pour ne pas redemander ces matchs.
3. **L'arrêter et tout recollecter avec le collecteur v2**, dans un format unique.

## Décision

Option 3.

- Arrêter l'ancien script dès maintenant (aucune perte : la collecte v2 repart de zéro).
- **Ne pas exporter** le contenu de `raw.api_football_fixture_detail` : il reste en base comme copie de secours, sans être supprimé.
- Le collecteur v2 (ADR-0004) recollecte tout, y compris ces matchs, directement dans le format de l'ADR-0003.
- **Export unique en fin de collecte** : la sauvegarde sur disque externe a lieu une seule fois, au gel des données (ADR-0006).

## Conséquences

- Un format de brut unique, produit par un seul code : pas de script de conversion à écrire ni à maintenir.
- Coût : environ 1 000 requêtes, soit moins de 1 % du quota restant.
- Règle à respecter jusqu'au gel : **ne jamais lancer `docker compose down -v`**, et ne pas supprimer `data/raw/`.
- `ingestion/api_football.py` (raw vers staging) n'est **pas** exécuté tant que l'identification des joueurs n'est pas corrigée (rapport B.4, D1 et D3).
