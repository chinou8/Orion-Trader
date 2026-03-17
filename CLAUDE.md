# Orion Trader — Instructions pour Claude Code

## Contexte
Application de trading automatisé pilotée par un comité de 3 IA (Claude, GPT-4o, Grok).
Les agents débattent, votent, et exécutent des ordres de manière autonome sur Interactive Brokers.

## Stack
- Backend : FastAPI (port 8080), SQLite, Python, venv dans .venv/
- Frontend : Next.js
- VM : Google Cloud Linux
- Lancement backend : uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8080

## Règles importantes
- Ne jamais changer le port 8080
- Toujours travailler dans le venv : source .venv/bin/activate
- Après chaque modification, committer sur GitHub avec un message clair
- Ne jamais casser les tests pytest existants

## Ce qui existe déjà (ne pas recréer)
- 30+ endpoints FastAPI dans backend/app/api/routes.py
- Système proposals (PENDING → APPROVED → EXECUTED)
- SimulatorExecutionProvider fonctionnel
- Watchlist, news RSS, portfolio, equity curve

## Ce qui manque (priorités)
1. backend/app/decision/ — agents IA (Claude + GPT-4o + Grok) + comité de vote
2. backend/app/ibkr/ — connexion réelle IB Gateway via ib_insync
3. Frontend — dashboard style "Defend AI Broker" (noir/vert, graphiques temps réel)
