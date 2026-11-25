# Academic submission guide

This repository contains implementation code and handoff documentation. Complete this report with actual project-specific evidence; do not copy illustrative values or invent experimental results.

## Suggested report structure

1. Title page, declaration and acknowledgements (according to institutional format).
2. Abstract — problem, objective, approach, implemented modules and measured outcomes.
3. Introduction — problem statement, motivation, objectives, scope and constraints.
4. Literature review — food image classification, food composition datasets, nutrition calculation and knowledge graphs. Cite primary sources.
5. Requirements and methodology — functional/non-functional requirements, dataset licensing, system design and development process.
6. Architecture and implementation — frontend, FastAPI services, relational schema, USDA/IFCT data integration, image pipeline, nutrition calculation and recipe workflow.
7. Model development — dataset provenance, class taxonomy, split strategy, architecture, training settings, preprocessing and model export. Complete only after training.
8. Knowledge graph — ontology, graph database, ETL, queries and evaluation. Complete only after implementation.
9. Testing and evaluation — automated test results, manual test evidence, model metrics, nutrition calculation validation, performance and accessibility.
10. Results and discussion — measured outcomes, failure analysis, comparison with objectives and limitations.
11. Security, privacy, ethics and licensing.
12. Conclusion and future work.
13. References and appendices — setup guide, API examples, test logs, dataset/model cards and screenshots.

## Evidence checklist

- Record exact Git commit hash, date, Python/Node/Docker versions and environment.
- Attach the final backend test output and frontend lint/typecheck/build output.
- Include screenshots of actual running workflows, not mockups.
- Include USDA/IFCT data provenance and licenses.
- Include model training logs, test split definition, per-class metrics and confusion matrix after training.
- Include knowledge graph schema, data volume, query examples and evaluation after graph implementation.
- Include Docker build/start logs and the exact tested commands.
- Record known limitations honestly, including missing authentication or production controls if unresolved.

## Results table template

| Evaluation item | Method / dataset | Measured result | Evidence reference |
|---|---|---|---|
| Backend automated tests | pytest | Fill after execution | Attach log |
| Frontend typecheck | `npm run typecheck` | Fill after execution | Attach log |
| Frontend production build | `npm run build` | Fill after execution | Attach log |
| Food classifier | Held-out test set | Fill after training | Metrics and confusion matrix |
| Nutrition calculation | Hand-checked source records | Fill after validation | Calculation sheet |
| Knowledge graph | Defined graph benchmark | Fill after implementation | Query/evaluation log |
| Docker deployment | Docker Compose | Fill after target validation | Build and runtime logs |
