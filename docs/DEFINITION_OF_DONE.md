# Definition of Done — Bloc 0

Un item Bloc 0 est considéré terminé quand tous les points suivants sont validés:

1. **Monorepo en place**
   - Répertoires: `backend/`, `frontend/`, `infra/`, `docs/`.
2. **Backend opérationnel**
   - FastAPI minimal exposant `/health`.
   - Route `/` renvoyant une page HTML "Orion Trader – OK".
   - Écoute locale sur `127.0.0.1:8080`.
3. **SQLite initialisée automatiquement**
   - Création de `./data/orion.db` au démarrage.
   - Table `settings` créée si absente.
4. **Outillage local**
   - Installation via `python -m venv` + pip.
   - Commandes `run`, `test`, `lint` disponibles via Makefile/scripts.
5. **Qualité**
   - Lint backend (`ruff`) passe.
   - Tests backend (`pytest`) passent.
6. **CI GitHub Actions**
   - Pipeline simple sans déploiement: lint + tests + build.
7. **Sécurité du dépôt**
   - Aucun secret commité.
   - `.env.example` fourni.
   - `data/` et logs exclus du versioning.
8. **Documentation initiale**
   - README de setup/run/tests.
   - `docs/ARCHITECTURE.md` aligné sur le plan V1.
