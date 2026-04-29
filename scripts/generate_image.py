#!/usr/bin/env python3
"""Generate an image through the OpenAI-compatible API configured for Codex."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def load_base_url(home: Path, override: str | None) -> str:
    if override:
        return override.rstrip("/")
    env_url = os.environ.get("OPENAI_BASE_URL")
    if env_url:
        return env_url.rstrip("/")
    config_path = home / "config.toml"
    if config_path.exists():
        if tomllib is not None:
            with config_path.open("rb") as f:
                config = tomllib.load(f)
            provider = config.get("model_provider", "OpenAI")
            providers = config.get("model_providers", {})
            base_url = providers.get(provider, {}).get("base_url")
            if base_url:
                return str(base_url).rstrip("/")
        else:
            base_url = parse_base_url_without_tomllib(config_path)
            if base_url:
                return base_url.rstrip("/")
    return "https://api.openai.com/v1"


def parse_base_url_without_tomllib(config_path: Path) -> str | None:
    """Parse just enough TOML to find the active provider's base_url."""
    text = config_path.read_text()
    provider = "OpenAI"
    provider_match = re.search(r'(?m)^model_provider\s*=\s*"([^"]+)"', text)
    if provider_match:
        provider = provider_match.group(1)
    section = re.escape(f'model_providers.{provider}')
    pattern = rf'(?ms)^\[{section}\]\s*(.*?)(?=^\[|\Z)'
    section_match = re.search(pattern, text)
    if not section_match:
        return None
    base_match = re.search(r'(?m)^base_url\s*=\s*"([^"]+)"', section_match.group(1))
    return base_match.group(1) if base_match else None


def load_api_key(home: Path) -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    auth_path = home / "auth.json"
    if not auth_path.exists():
        raise SystemExit(f"Missing API key: set OPENAI_API_KEY or create {auth_path}")
    auth = json.loads(auth_path.read_text())
    key = auth.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit(f"Missing OPENAI_API_KEY in {auth_path}")
    return key


def add_if_present(payload: dict, key: str, value):
    if value is not None:
        payload[key] = value


def sniff_extension(data: bytes, requested_format: str | None) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if requested_format:
        normalized = requested_format.lower()
        return ".jpg" if normalized == "jpeg" else f".{normalized}"
    return ".img"


def request_json(url: str, key: str, payload: dict, timeout: int) -> tuple[int, dict, float]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    elapsed = time.time() - start
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"Non-JSON response from API, HTTP {status}: {exc}") from exc
    return status, parsed, elapsed


def download_url(url: str, timeout: int) -> tuple[bytes, str]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        content_type = resp.headers.get_content_type()
        return resp.read(), content_type


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size")
    parser.add_argument("--quality")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--response-format", dest="response_format", default="b64_json")
    parser.add_argument("--output-format", dest="output_format")
    parser.add_argument("--output-compression", dest="output_compression", type=int)
    parser.add_argument("--background")
    parser.add_argument("--moderation")
    parser.add_argument("--user")
    parser.add_argument("--base-url", help="Override Codex config base_url")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--prefix", default="codex_image")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--extra-json", help="JSON object merged into the request payload")
    parser.add_argument("--print-response-summary", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print endpoint and payload without calling the API")
    args = parser.parse_args()

    home = codex_home()
    base_url = load_base_url(home, args.base_url)

    payload: dict = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
    }
    add_if_present(payload, "size", args.size)
    add_if_present(payload, "quality", args.quality)
    add_if_present(payload, "response_format", args.response_format)
    add_if_present(payload, "output_format", args.output_format)
    add_if_present(payload, "output_compression", args.output_compression)
    add_if_present(payload, "background", args.background)
    add_if_present(payload, "moderation", args.moderation)
    add_if_present(payload, "user", args.user)
    if args.extra_json:
        extra = json.loads(args.extra_json)
        if not isinstance(extra, dict):
            raise SystemExit("--extra-json must be a JSON object")
        payload.update(extra)

    endpoint = f"{base_url}/images/generations"
    if args.dry_run:
        print(f"endpoint={endpoint}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    api_key = load_api_key(home)
    status, parsed, elapsed = request_json(endpoint, api_key, payload, args.timeout)
    if status >= 400 or parsed.get("error"):
        print(f"http_status={status}")
        print(json.dumps({"error": parsed.get("error", parsed)}, ensure_ascii=False, indent=2))
        return 1

    data_items = parsed.get("data") or []
    if not data_items:
        print(f"http_status={status}")
        print(json.dumps({"error": "response has no data items"}, ensure_ascii=False, indent=2))
        return 1

    first = data_items[0]
    image_bytes: bytes
    extension_hint = args.output_format
    if first.get("b64_json"):
        image_bytes = base64.b64decode(first["b64_json"])
    elif first.get("url"):
        image_bytes, content_type = download_url(first["url"], args.timeout)
        guessed = mimetypes.guess_extension(content_type)
        extension_hint = guessed.lstrip(".") if guessed else extension_hint
    else:
        print(f"http_status={status}")
        print(json.dumps({"error": "first data item has neither b64_json nor url"}, ensure_ascii=False, indent=2))
        return 1

    out_dir = args.output_dir or home / "generated_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = sniff_extension(image_bytes, extension_hint)
    out_path = out_dir / f"{args.prefix}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
    out_path.write_bytes(image_bytes)

    print(f"http_status={status}")
    print(f"time_total={elapsed:.3f}")
    print(f"saved={out_path}")
    print(f"bytes={len(image_bytes)}")
    print(f"markdown=![generated image]({out_path})")
    if args.print_response_summary:
        summary = {
            "created": parsed.get("created"),
            "data_len": len(data_items),
            "first_item_keys": sorted(first.keys()),
            "b64_json_len": len(first.get("b64_json") or ""),
            "has_url": bool(first.get("url")),
            "revised_prompt_present": bool(first.get("revised_prompt")),
            "revised_prompt_preview": (first.get("revised_prompt") or "")[:180],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
