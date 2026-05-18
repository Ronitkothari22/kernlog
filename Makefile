.PHONY: backend alerts migrate seed topics

backend:
	uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000} --reload

alerts:
	python -m alert_engine.main

migrate:
	python scripts/migrate.py

seed:
	python scripts/seed.py

topics:
	python scripts/topics.py
