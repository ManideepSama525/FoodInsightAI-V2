# Local setup

Requirements: Windows 11, PowerShell 5.1, Python 3.12, Node.js LTS, npm and Git.

Backend from repository root:
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn backend.app.main:app --reload
```
API docs: http://localhost:8000/docs

Frontend in a second PowerShell:
```powershell
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:3000

Quality checks:
```powershell
pytest
ruff check backend
```
In frontend: `npm run typecheck`, `npm run lint`, `npm run build`. Record results only after execution.
