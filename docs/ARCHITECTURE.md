# FoodInsightAI V2 architecture

```text
Browser
  |
  v
Next.js frontend
  |  local catalog / USDA search-import / portion calculation
  |  image upload / recipe creation
  v
FastAPI (/api/v1)
  |-- route and Pydantic schema layer
  |-- food composition and recipe services
  |-- image validation and recognition provider interface
  |      `-- optional TorchScript runtime (trained artifact supplied separately)
  |-- SQLAlchemy persistence
  |      |-- Food / FoodNutrient
  |      |-- Recipe / RecipeIngredient
  |      `-- AnalysisRecord
  `-- external USDA FoodData Central adapter

Alembic migrations manage the relational schema.
Docker Compose runs frontend and backend; persistent SQLite data/uploads use a named volume.
A future knowledge graph is a separate integration layer and is not present in this build.
```

Food and nutrient records preserve source identifiers, units, basis quantity and nullable nutrient amounts. Missing values remain null, not zero. Recipe nutrient aggregation propagates unknown values rather than reporting partial totals as complete. Upload validation checks byte limit, decoded image format, MIME agreement and dimension limits. Recognition uses an explicit provider interface and returns service unavailable until model artifacts are configured.
