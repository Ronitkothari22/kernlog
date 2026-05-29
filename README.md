# Kernlog Backend (Repo 1)

Backend-first workspace for Kernlog SaaS.

## Scope
- This repository is for the backend only (`kernlog-backend`).
- Frontend (`kernlog-frontend`) is intentionally deferred until backend stability.

## Python Version
- Target runtime: **Python 3.11**

## Local Setup
1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy env file and fill values:
   ```bash
   cp .env.example .env
   ```
4. Run backend API:
   ```bash
   make backend
   ```
5. Run alert worker:
   ```bash
   make alerts
   ```

## Process Runner
Use `honcho` to run API and worker together:
```bash
honcho start
```

## Make Targets
- `make backend` - start FastAPI app
- `make alerts` - start alert worker
- `make migrate` - run Alembic migrations to head
- `make seed` - seed dev org/user/agent key
- `make topics` - run topic setup script

## Neon Connectivity Note
- The `Makefile` sets a default `PGHOSTADDR=98.85.120.174` to force IPv4 and avoid local IPv6 routing issues with Neon pooler hosts.
- Override this any time, for example:
  ```bash
  PGHOSTADDR=<your-ipv4-address> make migrate
  ```
