"""
The wrapper around the Claude API.

Kept deliberately small. It sends one invoice, insists on JSON coming back, and
retries a handful of times when the API is briefly unavailable. Everything about
what to ask for lives in prompts.py and everything about what to do with the
answer lives in the control engine.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config as cfg
from src.extraction import prompts


@dataclass
class ExtractionResult:
    data: dict | None
    method: str
    model: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    attempts: int = 0
    error: str | None = None


def load_dotenv_if_present() -> None:
    """Read a plain .env file. Avoids a dependency for something this small."""
    env_file = cfg.ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key() -> str | None:
    load_dotenv_if_present()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return key or None


_client = None


def get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=api_key())
    return _client


def _parse_json(text: str) -> dict:
    """The reply is prefilled with an opening brace, so put it back on."""
    body = text.strip()
    if not body.startswith("{"):
        body = "{" + body
    # Trim anything the model added after the object closed.
    depth, end, in_str, esc = 0, None, False, False
    for i, ch in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(body[:end] if end else body)


def _call(messages: list, model: str) -> ExtractionResult:
    client = get_client()
    started = time.time()
    last_error = None

    for attempt in range(1, cfg.API_MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=cfg.CLAUDE_MAX_TOKENS,
                temperature=cfg.CLAUDE_TEMPERATURE,
                system=prompts.SYSTEM_PROMPT,
                messages=messages + [{"role": "assistant", "content": "{"}],
            )
            data = _parse_json(resp.content[0].text)
            return ExtractionResult(
                data=data,
                method="",
                model=model,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                seconds=round(time.time() - started, 2),
                attempts=attempt,
            )
        except Exception as exc:  # network blip, rate limit, or bad JSON
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < cfg.API_MAX_RETRIES:
                time.sleep(cfg.API_RETRY_BACKOFF ** attempt + random.uniform(0, 0.4))

    return ExtractionResult(
        data=None, method="", model=model,
        seconds=round(time.time() - started, 2),
        attempts=cfg.API_MAX_RETRIES, error=last_error,
    )


def extract_from_text(page_text: str, model: str | None = None) -> ExtractionResult:
    result = _call(
        [{"role": "user", "content": prompts.text_user_message(page_text)}],
        model or cfg.CLAUDE_MODEL,
    )
    result.method = "claude_text"
    return result


def extract_from_image(png_b64: str, model: str | None = None) -> ExtractionResult:
    content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": png_b64},
        },
        {"type": "text", "text": prompts.vision_user_message()},
    ]
    result = _call([{"role": "user", "content": content}], model or cfg.CLAUDE_MODEL)
    result.method = "claude_vision"
    return result


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = cfg.MODEL_PRICING.get(model)
    if not price:
        return 0.0
    return (input_tokens / 1_000_000 * price["input"]
            + output_tokens / 1_000_000 * price["output"])
