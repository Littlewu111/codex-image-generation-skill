---
name: codex-image-generation
description: Generate images through the OpenAI-compatible API configured in Codex, using the default base_url from ~/.codex/config.toml and API key from ~/.codex/auth.json, then save and display the result in the Codex desktop client. Use when a user asks Codex to generate, test, or show an image via their configured Codex API endpoint, or asks about image-generation parameters such as size, quality, response_format, output_format, background, moderation, or negative prompts.
---

# Codex Image Generation

## Core Rule

Use the user's existing Codex API configuration instead of asking for a key.

- Read `base_url` from `${CODEX_HOME:-$HOME/.codex}/config.toml`.
- Prefer the configured `model_provider` block, for example `[model_providers.OpenAI].base_url`.
- Read the API key from environment `OPENAI_API_KEY` first, then `${CODEX_HOME:-$HOME/.codex}/auth.json` field `OPENAI_API_KEY`.
- Never print or echo the API key.
- Save generated images under `${CODEX_HOME:-$HOME/.codex}/generated_images` unless the user asks for another location.
- Use `gpt-image-2` only. Do not retry with `gpt-image-1`, `dall-e-3`, `dall-e-2`, Gemini image models, or other image model names.
- The bundled script defaults to a 300 second request timeout to allow slow image generations to finish.
- In the Codex desktop client, display local images with an absolute-path Markdown image:

```markdown
![generated image](/absolute/path/to/image.png)
```

## Quick Start

Use the bundled script for the default workflow:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-image-generation/scripts/generate_image.py" \
  --prompt "A small blue circle centered on a white background, simple flat icon" \
  --model gpt-image-2 \
  --size 1024x1024 \
  --quality low \
  --response-format b64_json \
  --output-format png
```

The script prints `saved=...` and `markdown=...`. Put the printed Markdown image line in the final answer to show the image in Codex.

The bundled script defaults to curl for the HTTP transport because some gateways/WAFs reject Python `urllib` image requests with HTTP 403 while accepting the same payload from curl. Use `--transport urllib` only when explicitly testing the fallback path.
The script also rejects non-`gpt-image-2` model names locally before making a real API request.

## Manual Curl Pattern

Use this only when the script is not suitable. Keep the key in a shell variable and avoid command traces that reveal secrets.

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
BASE_URL="$(python3 - <<'PY'
import os, tomllib
home=os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
cfg=tomllib.load(open(os.path.join(home, "config.toml"), "rb"))
provider=cfg.get("model_provider", "OpenAI")
print(cfg.get("model_providers", {}).get(provider, {}).get("base_url", "https://api.openai.com/v1").rstrip("/"))
PY
)"
KEY="$(jq -r '.OPENAI_API_KEY' "$CODEX_HOME/auth.json")"
curl -sS "$BASE_URL/images/generations" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "A clean icon of a blue glass sphere on a plain background",
    "size": "1024x1024",
    "quality": "low",
    "n": 1,
    "response_format": "b64_json",
    "output_format": "png",
    "background": "opaque",
    "moderation": "auto"
  }'
```

Decode `data[0].b64_json` to a file before showing it:

```bash
jq -r '.data[0].b64_json' response.json | base64 -D > /absolute/path/image.png
```

On Linux, use `base64 -d` instead of macOS `base64 -D`.

## Parameter Guide

These are the common OpenAI-compatible image-generation parameters.

- `model`: Required. This skill only supports `gpt-image-2`; other model names are rejected locally.
- `prompt`: Required. Describe what to generate. Put "no text, no watermark, no clutter" in the prompt when negative constraints are needed.
- `n`: Number of images. Use `1` for smoke tests and cost control.
- `size`: Resolution or aspect setting. Common values: `1024x1024`, `1536x1024`, `1024x1536`, or `auto` when supported.
- `quality`: Generation quality. Common GPT Image values: `low`, `medium`, `high`, `auto`. Some DALL-E style channels use `standard` or `hd`.
- `response_format`: Use `b64_json` when the image must be saved and displayed locally. Some gateways may also support `url`.
- `output_format`: Encoded image format when supported: `png`, `jpeg`, or `webp`.
- `output_compression`: Integer `0-100`; useful for `jpeg` and `webp`, usually ignored for `png`.
- `background`: `opaque`, `transparent`, or `auto` when supported. Transparent output usually requires `png` or `webp`.
- `moderation`: Usually `auto` or `low` when supported.
- `user`: Optional end-user identifier for auditing.
- `style`, `watermark`, `extra_fields`: Gateway/model-specific. Use only when the target upstream documents support.

## Negative Prompts

Do not assume `negative_prompt` works on `/v1/images/generations`. In the local `new-api` code, the standard image request does not define `negative_prompt`; some non-OpenAI adapters may support it through vendor-specific payloads, but OpenAI-compatible pass-through paths may drop or ignore it.

Reliable pattern:

```text
A product photo of a blue glass sphere, centered, plain background. No text, no watermark, no people, no clutter.
```

Use vendor-specific `negative_prompt` only after inspecting the selected channel adapter or provider docs.

## Stability Test Pattern

When the user allows a limited number of real requests, count every `/images/generations` call. For a single broad smoke test, use:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-image-generation/scripts/generate_image.py" \
  --prompt "A clean product-style icon of a blue glass sphere on a plain light gray background, centered composition, no text, no watermark, no clutter" \
  --model gpt-image-2 \
  --size 1024x1024 \
  --quality low \
  --response-format b64_json \
  --output-format jpeg \
  --output-compression 82 \
  --background opaque \
  --moderation auto \
  --user codex-param-smoke-test \
  --timeout 300
```

Success criteria:

- HTTP request succeeds.
- Response has `data[0].b64_json` or `data[0].url`.
- Decoded/downloaded image file is non-empty and `file` reports the expected image type and dimensions.
- Final answer includes the absolute-path Markdown image so the Codex client renders it.

## Troubleshooting

- Codex normally stores the OpenAI-compatible API key in `${CODEX_HOME:-$HOME/.codex}/auth.json`.
- If the script gets HTTP 403, first retry with the default curl transport or confirm it was not forced to `--transport urllib`.
- If a different model returns `model_not_found`, do not keep trying fallback model names; this skill intentionally uses only `gpt-image-2`.
- If `gpt-image-2` returns HTTP 524, the request reached the gateway but timed out upstream. The script default is already 300 seconds; simplify the prompt, keep `quality low`, or use a gateway path without a shorter Cloudflare/proxy timeout.
- If the response is `url` but a client expects base64, retry with `--response-format b64_json` if the user permits another real request.
- If `output_format=jpeg` is used, expect a `.jpg`/JPEG file even when the response field is still named `b64_json`.
- If a field is accepted but seems ignored, the gateway may forward it while the upstream model ignores it.
- If a policy error occurs, simplify the prompt and avoid public figures, copyrighted characters, logos, or sensitive content before blaming connectivity.
