"""The MCP process and FreeCAD add-on must use the same token location."""

import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from freecad_addon.local_config import read_token as addon_read_token, token_path as addon_token_path
from freecad_mcp.config import initialize_token_file, read_token as client_read_token, token_path as client_token_path


class TokenPathTests(unittest.TestCase):
    def test_initialized_token_is_read_by_both_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"FREECAD_MCP_CONFIG_DIR": folder}, clear=True):
                with redirect_stdout(StringIO()):
                    initialize_token_file()
                self.assertEqual(client_read_token(), addon_read_token())

    def test_config_directory_override_is_shared(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "configured"
            with patch.dict(os.environ, {"FREECAD_MCP_CONFIG_DIR": str(directory)}, clear=True):
                expected = directory / "token"
                self.assertEqual(client_token_path(), expected)
                self.assertEqual(addon_token_path(), expected)

    def test_explicit_token_file_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            token = directory / "custom-token"
            with patch.dict(os.environ, {
                "FREECAD_MCP_CONFIG_DIR": str(directory / "config"),
                "FREECAD_MCP_TOKEN_FILE": str(token),
            }, clear=True):
                self.assertEqual(client_token_path(), token)
                self.assertEqual(addon_token_path(), token)

    def test_empty_token_file_uses_config_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "configured"
            with patch.dict(os.environ, {
                "FREECAD_MCP_CONFIG_DIR": str(directory),
                "FREECAD_MCP_TOKEN_FILE": "",
            }, clear=True):
                self.assertEqual(client_token_path(), directory / "token")
                self.assertEqual(addon_token_path(), directory / "token")


if __name__ == "__main__":
    unittest.main()
