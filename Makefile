PYTHON ?= python

.PHONY: install run test lint

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]

run:
	$(PYTHON) -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check backend
