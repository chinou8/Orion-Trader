# Orion Trader

Monorepo d'initialisation du projet **orion-trader** (fusion Orion Invest + bot de trading).

## Structure

- `backend/` : API FastAPI + logique métier future
- `frontend/` : espace réservé front-end dashboard
- `infra/` : scripts d'installation/exécution/tests/lint
- `docs/` : architecture, DoD, décisions produit/techniques

## Prérequis

- Python 3.10+
- `python -m venv` (Windows/Linux)

## Setup local

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
make install
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Lancer le backend

```bash
make run
```

- API: `http://127.0.0.1:8080/health`
- Page minimale: `http://127.0.0.1:8080/`
- Base SQLite: `./data/orion.db` (créée automatiquement au démarrage)


## Déploiement VM Linux (GCP)

Ce flux permet de déployer le backend sur une VM Linux en évitant toute dépendance à un setup local.

```bash
git clone git@github.com:chinou8/Orion-Trader.git
cd Orion-Trader
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080
```

- Healthcheck backend: `http://127.0.0.1:8080/health`
- SQLite: `./data/orion.db` (créée automatiquement)

### Tunnel SSH (exemple)

Depuis votre machine locale vers la VM:

```bash
ssh -N -L 8080:127.0.0.1:8080 <user>@<vm-ip-ou-dns>
```

Ensuite, ouvrez `http://127.0.0.1:8080/health` dans votre navigateur local.

## Tests et lint

```bash
make lint
make test
```

ou via scripts shell:

```bash
./infra/scripts/lint.sh
./infra/scripts/test.sh
```

## Variables d'environnement

Copier `.env.example` vers `.env` puis adapter si nécessaire.

## CI

GitHub Actions (`.github/workflows/ci.yml`) exécute:
- lint (`ruff`)
- tests (`pytest`)
- build léger (`python -m compileall backend`)
