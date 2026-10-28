"""Regression checks for the local validation entry point."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which("bash"), "local validation requires bash")
class LocalValidationTests(unittest.TestCase):
    def test_missing_requested_interpreter_is_not_masked_by_an_old_venv(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "check-local.sh"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "scripts").mkdir()
            shutil.copy(script, root / "scripts" / "check-local.sh")
            old_python = root / ".venv" / "bin" / "python"
            old_python.parent.mkdir(parents=True)
            old_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            old_python.chmod(0o755)
            env = dict(os.environ, PYTHON=str(root / "missing-python"))
            result = subprocess.run(
                ["bash", str(root / "scripts" / "check-local.sh")],
                env=env, text=True, capture_output=True, check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Local FreeCAD MCP checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
