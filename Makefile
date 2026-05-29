.PHONY: backend alerts migrate seed topics
PYTHON := python3
export PGHOSTADDR ?= 98.85.120.174

ifneq ("$(wildcard venv/bin/python)","")
PYTHON := venv/bin/python
endif

backend:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000} --reload

alerts:
	$(PYTHON) -m alert_engine.main

migrate:
	$(PYTHON) scripts/migrate.py

seed:
	$(PYTHON) scripts/seed.py

topics:
	$(PYTHON) scripts/topics.py
