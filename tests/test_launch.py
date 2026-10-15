import io
import json
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import launch
import app


class LauncherTests(unittest.TestCase):
    @patch("launch.webbrowser.open")
    @patch("launch.urllib.request.build_opener")
    def test_reuses_running_atlas(self, build, browser):
        response = io.BytesIO(
            json.dumps({"app": "atlas", "version": 3, "status": "ok"}).encode()
        )
        build.return_value.open.return_value = response
        with patch.dict(os.environ, {"PORT": "8000"}):
            launch.main()
        browser.assert_called_once_with("http://127.0.0.1:8000")

    @patch("app.serve")
    @patch("launch.socket.socket")
    @patch("launch.urllib.request.build_opener")
    def test_port_collision_selects_ephemeral_port(self, build, sock, serve):
        build.return_value.open.side_effect = OSError("No server")
        sock.return_value.__enter__.return_value.bind.side_effect = OSError("Busy")
        with patch.dict(os.environ, {"PORT": "8000"}):
            launch.main()
        self.assertEqual(serve.call_args.args[:2], ("127.0.0.1", 0))
        self.assertTrue(callable(serve.call_args.args[2]))

    def test_batch_has_windows_line_endings_and_quoted_paths(self):
        content = (
            Path(__file__).resolve().parents[1] / "Iniciar Atlas.bat"
        ).read_bytes()
        self.assertNotIn(b"\n", content.replace(b"\r\n", b""))
        self.assertIn(b'cd /d "%~dp0"', content)
        self.assertIn(b'"%~dp0launch.py"', content)
        self.assertIn(b"sys.version_info >= (3,12)", content)


if __name__ == "__main__":
    unittest.main()
