# Local validation
GitHub Actions CI was retired in favor of explicit local validation.

Run from repository root (Linux/macOS/WSL):
```sh
bash scripts/check-local.sh
```
This creates/reuses `.venv`, installs the project in editable mode, runs its unit tests, and compiles the source and FreeCAD addon modules. Run against the exact commit under review and capture the command, Python version, host, and exit code in the PR. A passing review does not imply these commands have been executed.

No GitHub Actions workflow is used for validation.
