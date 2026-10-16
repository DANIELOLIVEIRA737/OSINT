import base64
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "ATLAS_REQUIRE_AUTH": "1",
                "ATLAS_ADMIN": "atlas",
                "ATLAS_PASSWORD": "test-only-password-12345",
            },
        )
        self.environment.start()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.environment.stop()

    def request(self, path, authorization=None, data=None):
        headers = {"Authorization": authorization} if authorization else {}
        return urllib.request.urlopen(
            urllib.request.Request(self.base + path, headers=headers, data=data)
        )

    def test_every_workspace_entry_requires_authentication(self):
        for path, data in [
            ("/", None),
            ("/cti/", None),
            ("/app.js", None),
            ("/api/projects", None),
            ("/api/projects", b"{}"),
            ("/health", b"{}"),
        ]:
            with self.subTest(path=path, post=data is not None):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.request(path, data=data)
                self.assertEqual(caught.exception.code, 401)
                self.assertIn("Basic", caught.exception.headers["WWW-Authenticate"])

    def test_credentials_and_public_healthcheck(self):
        self.assertEqual(json.load(self.request("/health"))["status"], "ok")
        good = "Basic " + base64.b64encode(b"atlas:test-only-password-12345").decode()
        self.assertEqual(self.request("/", good).status, 200)
        for bad in [
            "Bearer token",
            "Basic !!!",
            "Basic " + base64.b64encode(b"atlas:wrong").decode(),
        ]:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request("/", bad)
            self.assertEqual(caught.exception.code, 401)

    def test_required_authentication_fails_closed(self):
        with patch.dict(os.environ, {"ATLAS_PASSWORD": ""}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request("/")
            self.assertEqual(caught.exception.code, 401)
            with self.assertRaisesRegex(ValueError, "16"):
                app.serve(port=0)
