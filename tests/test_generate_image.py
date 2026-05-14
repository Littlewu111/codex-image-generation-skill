#!/usr/bin/env python3
"""Tests for the image generation helper."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
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

    def test_cli_rejects_non_gpt_image_2_models_before_request(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--prompt",
                "test",
                "--model",
                "dall-e-3",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Only gpt-image-2 is supported", result.stderr)

    def test_cli_default_timeout_is_five_minutes(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--prompt",
                "test",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn('"model": "gpt-image-2"', result.stdout)
        self.assertIn("timeout=300", result.stdout)


if __name__ == "__main__":
    unittest.main()
