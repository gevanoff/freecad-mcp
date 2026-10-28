# Local validation
GitHub Actions CI was retired in favor of explicit local validation.

Run from repository root (Linux/macOS/WSL):
```sh
bash scripts/check-local.sh
```
The script creates or reuses a separate ignored environment under `.venv-checks/` for each selected Python installation, installs the project in editable mode, runs its unit tests, and compiles the source and FreeCAD addon modules. Set `PYTHON` to the interpreter to validate, for example `PYTHON=python3.10 bash scripts/check-local.sh` followed by `PYTHON=python3.12 bash scripts/check-local.sh`. The script prints the interpreter used and refuses to reuse a mismatched environment. An old `.venv` is left untouched.

Run against the exact commit under review and capture the command, Python version, host, and exit code in the PR. A passing review does not imply these commands have been executed.

No GitHub Actions workflow is used for validation.
