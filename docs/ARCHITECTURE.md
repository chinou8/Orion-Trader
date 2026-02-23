# Architecture V1 (Bloc 0)

## Vision d'hébergement

- Déploiement cible plus tard sur VM Linux GCP.
- Démarrage avec dashboard accessible via tunnel SSH.
- URL publique + authentification ajoutées dans une phase ultérieure.

## Intégrations de trading

- Broker: IBKR via TWS API en passant par IB Gateway.
- Univers principal: actions/ETF avec exécution automatique.
- Type d'ordre par défaut: `LIMIT`.
- Quota standard: 8 ordres/jour.
- Boost opportunité “avérée”:
  - >= 4% pour actifs liquides,
  - >= 10% pour actifs moins liquides,
  - quota maximal alors porté à 10/jour.

## Obligations

- Mode par défaut: exécution manuelle après validation dashboard.
- Option `Bonds Auto` activable.
- Plafond d'allocation obligations: 25%.

## Scan et marchés

- Scan continu 24/7.
- Exécutions uniquement quand les marchés sont ouverts.
- Europe activée par défaut.
- US activable via un toggle.

## Signaux et horizon

- RSS institutionnels en Mode 1 (tech-only).
- Indicateurs supportés: SMA20/50, RSI14, volatilité.
- Horizon affiché: fenêtre unique (scénario A).

## Agents

- Deux agents opérables: `LIVE` et `SHADOW`.
- Switch opérationnel prévu entre les deux modes.

## Stockage

- Base locale SQLite sur disque (`./data/orion.db`) pour la phase actuelle.
- Cible ultérieure: disque persistant en environnement déployé.
- Données prévues: logs, reflections, mémoire Orion.
