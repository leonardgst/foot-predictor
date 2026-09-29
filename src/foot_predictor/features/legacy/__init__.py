"""Anciens modules de variables, remplacés en partie 3 (ADR-0030) ; retrait prévu en partie 4.

Gardés tant que `modeling/` (ancien, non exécuté en partie 3) les importe. Ils lisent
`staging.match` directement, sans la porte du scellé : ne pas les utiliser pour de nouvelles
variables (ADR-0028).
"""
