$ErrorActionPreference = "Stop"
python -m compileall backend
python -m pytest backend/tests -q
python -m ruff check backend
