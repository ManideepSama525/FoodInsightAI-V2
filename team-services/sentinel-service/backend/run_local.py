"""Start restricted Sentinel demo on localhost, never on the LAN."""
import os
from pathlib import Path
import sys
import uvicorn

if __name__ == "__main__":
    data = Path.home() / ".foodinsightai" / "sentinel-data"
    data.mkdir(parents=True, exist_ok=True)
    os.chdir(data)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    uvicorn.run("safe_demo_app:app", host="127.0.0.1", port=8010)
