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

## Module Settings (Bloc 3)

- Persistance des paramètres applicatifs dans SQLite (`settings` table, clé `app_settings`).
- API backend:
  - `GET /api/settings` : retourne la configuration complète.
  - `PUT /api/settings` : valide puis persiste la configuration complète.
- Validation appliquée côté backend:
  - types stricts (bool/int/float/string enum `LIMIT`),
  - bornes `0..1` pour seuils/cap/divergence,
  - `max_trades_per_day >= 0`,
  - `boost_trades_per_day >= max_trades_per_day`.
- Frontend Next.js:
  - page `/settings` pour charger/éditer/sauvegarder ces paramètres via `NEXT_PUBLIC_BACKEND_URL`.

## Module Chat Orion (Bloc 4)

- Persistance SQLite:
  - `chat_threads(id, title, created_at)`
  - `chat_messages(id, thread_id, role[user|orion], content, created_at)`
- Endpoints API:
  - `POST /api/chat/thread` : crée un thread (titre optionnel).
  - `GET /api/chat/thread/{thread_id}` : retourne le thread + messages ordonnés.
  - `POST /api/chat/thread/{thread_id}/message` : stocke le message user, génère et stocke la réponse Orion.
- Réponse Orion V0 mock:
  - structure JSON fixe `{reply_text, recommendations, watch_requests, meta}`
  - mode `tech-only` + timestamp
  - règles simples sur mots-clés (ex: "surveille" => watch request).
