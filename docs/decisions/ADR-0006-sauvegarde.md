# ADR-0006 — Sauvegarde des données brutes

- **Statut** : acceptée
- **Date** : 2026-09-27
- **Référence** : rapport de cadrage, C.6, G.4, G.11, décision M6

## Contexte

Après la fin de l'abonnement (2026-10-22), une perte du brut API-FOOTBALL serait irrémédiable. Avant cette date, une perte se répare par une recollecte peu coûteuse (quota abondant).

Préférence exprimée : un export unique, une fois toute la collecte terminée.

## Options envisagées

1. Sauvegardes au fil de la collecte (après chaque palier).
2. **Une sauvegarde unique au gel des données**, avec une marge suffisante pour recollecter en cas de problème.

## Décision

Option 2.

- **Sauvegarde unique le 19 octobre** (ADR-0005) : copie de `data/raw/` (fichiers et journaux de requêtes) sur le **disque dur externe**.
- **Test de restauration le même jour** : recopie depuis le disque externe dans un dossier vide, et vérification des sha256 du journal de requêtes. Les 20 et 21 octobre servent de marge si quelque chose manque.
- Recommandé, facultatif : une seconde copie hors de la maison, en archive chiffrée (7-Zip AES) sur un cloud gratuit.

## Conséquences

- Jusqu'au 19 octobre, la seule copie est celle du portable. Le risque est accepté, puisque tout se recollecte tant que l'abonnement est actif.
- Deux règles pour que ce risque reste faible : ne jamais lancer `docker compose down -v`, ne jamais supprimer `data/raw/`.
- Une commande (ou un court script documenté) de copie et de vérification sera fournie avec le collecteur v2.
- Les données ne sont jamais versionnées dans Git (licences, volume).
