# FoodInsightAI V2

FoodInsightAI V2 is a third-year academic project combining food recognition, nutrition analysis, food-safety checks, personal food records, recipe workflows, and a food knowledge graph.

This repository contains the current development milestone. It is an active academic project; not every planned research capability is complete.

## Implemented capabilities

- FastAPI backend with authenticated user workflows.
- Food catalog search and USDA FoodData Central integration.
- Nutrient calculations with unknown values retained as unknown.
- Food image preprocessing and TorchScript classification integration.
- Deterministic food-safety checks for known allergy, dietary, and preference conflicts.
- Personal food profiles, diary records, and user-scoped recipe workflows.
- Neo4j knowledge graph foundation for food, nutrient, recipe, and ingredient relationships.
- Personalized food recommendations.
- Portion-based nutrition calculations with quantity-source provenance.
- Responsive Next.js, React, and TypeScript frontend.
- Docker Compose deployment configuration and backend automated tests.

## Recognition and model status

A Food-101 EfficientNetV2-S baseline classifier was trained and evaluated during development. The reported baseline reached approximately 87.6% top-1 and 97.6% top-5 accuracy on the official Food-101 test split.

Trained model weights and datasets are intentionally excluded from this repository. Model artifacts must be supplied separately using the configured environment paths.

The current classifier is a single-label baseline. It is not a multi-food object detector. Image-derived portion estimation is not yet implemented.

## Remaining work

- Multi-food detection and localization.
- Indian-food-specific model training and evaluation.
- Improved image-based portion estimation.
- Hybrid retrieval combining SQL, graph, and vector retrieval.
- Evidence aggregation, source-conflict handling, and claim verification.
- Additional end-to-end, deployment, and user-acceptance validation.
- Final academic documentation, presentation, and demonstration preparation.

Model training and evaluation remain explicit project workstreams. Training data and model binaries are excluded from GitHub because of their size and data-provenance considerations.

## Repository structure

- `backend/` — FastAPI application, services, migrations, and tests.
- `frontend/` — Next.js application.
- `docs/` — architecture, setup, security, evaluation, training, and project documentation.
- `scripts/` — dataset preparation and utility scripts.
- `training/` — model training, evaluation, and analysis scripts.
- `docker-compose.yml` — local container orchestration.

## Local setup

Requirements: Python 3.12, Node.js 22, npm, and optionally Docker Desktop.

Create a local environment file by copying `.env.example` to `.env`. Configure local values as required. Never commit `.env` or production credentials.

### Docker

From the repository root, run:

    docker compose build
    docker compose up -d

Apply database migrations using `docs/DOCKER_DEPLOYMENT.md`.

Frontend: http://localhost:3000

Backend: http://localhost:8000

### Backend tests

Install project and development dependencies, then run:

    python -m pytest backend/tests -q

### Frontend checks

From the `frontend/` directory, run:

    npm ci
    npm run typecheck
    npm run lint
    npm run build

Only report checks as passed after they have actually run in the target environment.

## Data, secrets, and artifacts

Datasets, local databases, uploads, environment files, backups, caches, and trained model binaries are excluded from this repository. Obtain datasets from their original sources and verify their licenses and provenance before use.

Never commit API keys, passwords, access tokens, private keys, or production environment files.

## Project documentation

See `docs/` for architecture, setup, nutrition calculations, recognition, model training, knowledge graph, security, evaluation, deployment, and academic submission guidance.