# Test suite

Install the package and development dependencies with `python -m pip install -e ".[dev]"`, then run from the repository root:

```powershell
python -m pytest -q
```

Research and application API tests are kept together. Application tests construct isolated temporary SQLite databases and recording directories; they do not use the user's configured `~/.batsight` data. Synthetic tests are deterministic and do not access the internet or external datasets.
