# Docker deployment guide

## Prerequisites

- Docker Desktop with Docker Compose v2.
- A copied `.env` file based on `.env.example`.
- For recognition inference, trained TorchScript model and matching class-label JSON in `artifacts/`.

## Start

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

Open the frontend at `http://localhost:3000`. The API is at `http://localhost:8000`; in development, API docs are at `/docs`. Production mode disables interactive docs.

## Database migration

The backend image contains Alembic and an initial schema migration. Apply it once before using the application:

```powershell
docker compose run --rm backend alembic upgrade head
```

Then start/restart the services:

```powershell
docker compose up -d
```

The SQLite database and uploaded files persist in the `foodinsightai_data` named volume. Model artifacts are mounted read-only from the host `artifacts/` directory. The `artifacts/` directory is ignored by Git.

## Stop and inspect

```powershell
docker compose logs -f
docker compose down
```

`docker compose down -v` deletes the persistent database/upload volume. Do not use it unless intentionally resetting local data.

## Configuration notes

- `CORS_ORIGINS` must list the browser-visible frontend origin, normally `http://localhost:3000` for this local Compose setup. Production must use the actual HTTPS frontend origin.
- `NEXT_PUBLIC_API_BASE_URL` is compiled into the Next.js browser bundle at build time. Change the Compose build argument and rebuild the frontend when changing the public API URL.
- The default Compose database is SQLite for a single-instance academic demonstration. Use PostgreSQL and a managed backup strategy for multi-user production.
- The backend container runs as a non-root user. Verify volume permissions on the target Docker Desktop installation.
- This Compose stack is a deployment handoff, not a claim of production readiness. Review `docs/SECURITY_QA.md` first.
