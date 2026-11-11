# Backend entry point

The FastAPI application is implemented in `src/batsight/application/` so it can import and wrap the existing scientific package without moving modules.

From the repository root on Windows PowerShell:

```powershell
python -m pip install -e ".[dev]"
$env:BATSIGHT_DATA_DIR = "$env:LOCALAPPDATA\BatSight" # optional
python -m batsight.application
```

OpenAPI: `http://127.0.0.1:8000/docs`. Set `BATSIGHT_HOST`/`BATSIGHT_PORT` to change the listener, and `BATSIGHT_DATA_DIR` to change storage. The initial runnable experiment is forward synthetic simulation only. See `docs/application_architecture.md` and `docs/api_reference.md`.
