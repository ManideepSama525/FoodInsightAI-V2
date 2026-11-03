# FoodInsightAI V2

FoodInsightAI V2 is a third-year academic project for food image recognition, food composition lookup, nutrition calculation and recipe analysis.

## Repository structure

- `backend/` — FastAPI, SQLAlchemy models, Alembic migrations, service integrations and tests.
- `frontend/` — Next.js, React, TypeScript and Tailwind application.
- `docs/` — architecture, data provenance, API, evaluation, security, training and graph handoff documentation.
- `scripts/` — PowerShell setup and validation helpers.
- `docker-compose.yml` — local container orchestration.

## Implemented application workflows

- Local food catalog search and USDA FoodData Central search/import.
- IFCT-derived CSV import support for data supplied with appropriate rights/licensing.
- Food nutrient calculation by gram portion, retaining unknown nutrient values as null.
- Recipe creation from catalog ingredients and per-serving nutrient aggregation.
- Food image preprocessing and pluggable TorchScript inference interface.
- Responsive frontend for food search, import, image upload and recipe workflows.

## Important unfinished project work

- A trained food classifier is not included. Recognition returns HTTP 503 until a compatible model and class-label JSON are provided.
- No populated knowledge graph or graph database is included. See `docs/KNOWLEDGE_GRAPH_HANDOFF.md`.
- Real IFCT dataset import requires the project owner to provide licensed source data.
- No user authentication, authorization, distributed rate limiting or malware scanning is implemented. Review `docs/SECURITY_QA.md` before any public deployment.
- Frontend production build and Docker deployment must be verified on the target machine.

## Local setup

Requirements: Python 3.12, Node.js 22 LTS, npm and Git. Docker Desktop is optional.

Backend (PowerShell, repository root):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest backend/tests -q
uvicorn backend.app.main:app --reload
```

Frontend (second PowerShell window):

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Backend API is at `http://localhost:8000`; interactive docs are at `/docs` in development.

## Docker

```powershell
Copy-Item .env.example .env
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

Open `http://localhost:3000`. See `docs/DOCKER_DEPLOYMENT.md`.

## Verification

Backend:

```powershell
python -m compileall backend
python -m pytest backend/tests -q
python -m ruff check backend
```

Frontend, from `frontend/`:

```powershell
npm ci
npm run typecheck
npm run lint
npm run build
```

Only report checks as passed after they have actually run in the target environment.

## Project documentation

- `docs/ARCHITECTURE.md`
- `docs/LOCAL_SETUP.md`
- `docs/PROJECT_ROADMAP.md`
- `docs/NUTRITION_DATA.md`
- `docs/NUTRITION_CALCULATIONS.md`
- `docs/RECOGNITION_API.md`
- `docs/MODEL_TRAINING_HANDOFF.md`
- `docs/KNOWLEDGE_GRAPH_HANDOFF.md`
- `docs/INTEGRATION_EVALUATION.md`
- `docs/SECURITY_QA.md`
- `docs/DOCKER_DEPLOYMENT.md`
- `docs/ACADEMIC_SUBMISSION_GUIDE.md`
