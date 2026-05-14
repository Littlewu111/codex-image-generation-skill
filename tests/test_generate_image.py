#!/usr/bin/env python3
"""Tests for the image generation helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.py"
spec = importlib.util.spec_from_file_location("generate_image", SCRIPT)
generate_image = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(generate_image)


class RequestJsonTests(unittest.TestCase):
    def test_request_json_defaults_to_curl_without_leaking_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            body_path = Path(tmp) / "body.json"
            body_path.write_text('{"data":[{"b64_json":"abc"}]}')

            completed = mock.Mock()
            completed.returncode = 0
            completed.stdout = "http_code=200\n"
            completed.stderr = ""

            with mock.patch.object(generate_image.shutil, "which", return_value="/usr/bin/curl"):
                with mock.patch.object(generate_image.subprocess, "run", return_value=completed) as run:
                    status, parsed, _elapsed = generate_image.request_json(
                        "https://api.example.test/v1/images/generations",
                        "secret-token",
                        {"model": "gpt-image-2", "prompt": "test"},
                        180,
                        body_path=body_path,
                    )

        self.assertEqual(status, 200)
        self.assertEqual(parsed["data"][0]["b64_json"], "abc")
        args = run.call_args.args[0]
        self.assertEqual(args[0], "/usr/bin/curl")
        self.assertIn("--config", args)
        self.assertNotIn("secret-token", args)
        self.assertNotIn("secret-token", completed.stdout)


if __name__ == "__main__":
    unittest.main()
