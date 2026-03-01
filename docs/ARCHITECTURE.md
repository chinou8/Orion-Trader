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

## Module Watchlist (Bloc 5)

- Persistance SQLite:
  - `watchlist_items(id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at)`
- Endpoints API:
  - `GET /api/watchlist` : retourne les items actifs.
  - `POST /api/watchlist` : ajoute un item (symbol requis).
  - `PUT /api/watchlist/{id}` : met à jour un item (notes, active/inactive, etc.).
  - `DELETE /api/watchlist/{id}` : soft delete (`is_active=false`).
- Intégration Chat Orion:
  - lors de `POST /api/chat/thread/{thread_id}/message`, les `watch_requests` sont analysées,
  - les symboles détectés sont créés en watchlist si absents/inactifs,
  - la réponse inclut `watchlist_created` avec les items nouvellement créés.

## Module RSS Institutionnels + News (Bloc 6)

- Persistance SQLite:
  - `rss_feeds(id, name, url, is_active, created_at, updated_at)`
  - `news_items(id, feed_id, guid, title, link, published_at, summary, raw_json, created_at)`
  - contrainte d'unicité: `(feed_id, guid)` pour la déduplication.
- Service RSS/Atom:
  - parsing via `feedparser`,
  - dédup guid (fallback `link|title` si guid absent).
- Endpoints API:
  - `GET /api/rss/feeds`
  - `POST /api/rss/feeds`
  - `PUT /api/rss/feeds/{id}`
  - `POST /api/rss/fetch`
  - `GET /api/news?limit=50`
- Intégration Chat Orion:
  - si l'utilisateur demande "news" ou "marché", la réponse mock inclut `news_brief` (top 3 titres récents).

## Module Market Data (Bloc 7)

- Source V1: Stooq daily CSV (`https://stooq.com/q/d/l/?s={symbol}&i=d`).
- Persistance SQLite:
  - `market_bars(id, symbol, timeframe, ts, open, high, low, close, volume, source, created_at)`
  - contrainte unique `(symbol, timeframe, ts, source)`.
- Endpoints API:
  - `POST /api/market/fetch?symbol=XXX`
  - `GET /api/market/bars?symbol=XXX&limit=200`
  - `GET /api/market/indicators?symbol=XXX`
  - `POST /api/market/fetch_watchlist`
- Indicateurs V1:
  - SMA20 / SMA50 (close)
  - RSI14
  - volatilité (stddev des returns 20 périodes)
  - `horizon_hint` basé sur SMA/RSI/volatilité.
- Intégration Chat Orion (tech-only):
  - requête "analyse <symbol>" ajoute un bloc `market_analysis` (trend, RSI, vol, horizon).

## Module Trade Proposals (Bloc 8)

- Persistance SQLite:
  - `trade_proposals(id, created_at, updated_at, symbol, asset_type, market, side, qty, notional_eur, order_type, limit_price, horizon_window, thesis_json, status, approved_by, approved_at, notes)`
- Endpoints API:
  - `GET /api/proposals?status=...&limit=100`
  - `POST /api/proposals`
  - `PUT /api/proposals/{id}`
  - `POST /api/proposals/{id}/approve`
  - `POST /api/proposals/{id}/reject`
- Règles V1:
  - `order_type=LIMIT` par défaut.
  - BOND reste `PENDING` tant qu'il n'est pas approuvé explicitement.
- Intégration Chat Orion (tech-only):
  - messages `propose un trade sur <symbol>` / `acheter <symbol>` créent une proposition avec `horizon_window` dérivé des indicateurs et exposent `proposal_created` dans la réponse Orion.

## Module Execution Simulator (Bloc 9)

- Persistance SQLite:
  - `simulated_trades(id, proposal_id, symbol, side, qty, price, ts, fees_eur, slippage_bps, source, created_at)`
  - `portfolio_state(id, ts, cash_eur, equity_eur, unrealized_pnl_eur, realized_pnl_eur, created_at)`
  - `reflections(id, ts, proposal_id, text, json_payload, created_at)`
- Settings simul:
  - `simulator_initial_cash_eur` (10000)
  - `simulator_fee_per_trade_eur` (1.25)
  - `simulator_slippage_bps` (5)
- Endpoints API:
  - `POST /api/proposals/{id}/execute_simulated`
  - `GET /api/portfolio`
  - `GET /api/trades?limit=200`
  - `GET /api/reflections?limit=200`
- Règles V1:
  - exécution simulée autorisée uniquement pour proposals `APPROVED` et `asset_type in (EQUITY, ETF)`.
  - prix de référence = dernier `market_bars.close`.
  - slippage + fees appliqués, puis proposal mise à `EXECUTED`.
  - reflection structurée créée après trade (horizon, qualité des données, améliorations).

## Module Equity Curve & Performance (Bloc 10)

- Endpoints API:
  - `GET /api/portfolio/equity_curve?limit=500`
    - retourne la série triée par `ts` avec: `ts`, `equity_eur`, `cash_eur`, `realized_pnl_eur`, `unrealized_pnl_eur`.
  - `GET /api/portfolio/performance_summary`
    - retourne `current_equity_eur`, `performance_since_start_pct`, `trades_count`, `pnl_total_eur`.
- Source des données:
  - `portfolio_state` alimenté à chaque `execute_simulated`.
  - `simulated_trades` pour le nombre de trades.
- Frontend:
  - Dashboard `/` affiche une courbe d'equity simplifiée + résumé de performance.
  - `/portfolio` affiche la courbe complète + résumé.

## Module ExecutionProvider (Bloc 11)

- Objectif: abstraire l'exécution avant intégration IBKR réelle.
- Providers:
  - `SimulatorExecutionProvider`: exécute via simulateur interne existant.
  - `IbkrExecutionProvider` (stub): renvoie `IBKR not configured` avec consigne de config VM ultérieure.
- Settings:
  - `execution_mode`: `SIMULATED` | `IBKR_PAPER` | `IBKR_LIVE` (default `SIMULATED`).
- Endpoints API:
  - `GET /api/execution/status` -> mode courant + état provider.
  - `POST /api/proposals/{id}/execute` -> route générique via provider actif.
  - `POST /api/proposals/{id}/execute_simulated` conservé pour compat/debug.
