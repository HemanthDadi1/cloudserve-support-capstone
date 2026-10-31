"""Model access: the one place that handles retries, fallbacks, caching and the outage signal (FR-11).

Models are tried in order (MODEL_NAME, then MODEL_FALLBACKS), each with a short retry. Callers catch
LLMUnavailable and escalate instead of failing. Responses are cached on disk by (model list, system,
user), which saves free-tier quota and makes reruns reproducible.
Fallbacks chosen 31 Oct: the free models that returned a valid PR-01 answer while Flint was down.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
CACHE = Path(os.getenv("LLM_CACHE_PATH", str(ROOT / "storage/llm_cache")))
URL = "https://openrouter.ai/api/v1/chat/completions"
RETRIES, TIMEOUT = 2, 60  # per model
DEFAULT_FALLBACKS = "nvidia/nemotron-3.5-super-vl:free,xingchen-agi/xing4.0-29b-a4b:free"


def models() -> list[str]:
    fallbacks = [m.strip() for m in os.getenv("MODEL_FALLBACKS", DEFAULT_FALLBACKS).split(",") if m.strip()]
    return [os.getenv("MODEL_NAME", "recursive/flint-v1.0:free")] + fallbacks


class LLMUnavailable(Exception):
    pass


def load_prompt(name: str) -> dict:
    head, system, user = re.split(r"---SYSTEM---\n|---USER---\n", (PROMPTS / name).read_text())
    meta = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    return {**meta, "system": system.strip(), "user": user}


def render(template: str, **values: str) -> str:
    # str.replace, not str.format: the prompts contain literal JSON braces.
    for k, v in values.items():
        template = template.replace("{" + k + "}", v)
    return template


def complete(system: str, user: str, sleep=time.sleep) -> dict:
    """{"content": model text, "model": the model that produced it}."""
    key, chain = os.getenv("OPENROUTER_API_KEY"), models()
    path = CACHE / f"{hashlib.sha256(json.dumps([chain, system, user]).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not key:
        raise LLMUnavailable("OPENROUTER_API_KEY is not set")
    errors = []
    # shortcut: no circuit breaker, so a full outage costs ~10-20 s per model call; add one if runs get slow.
    for model in chain:
        last = None
        for attempt in range(RETRIES):
            try:
                r = requests.post(URL, timeout=TIMEOUT, headers={"Authorization": f"Bearer {key}"}, json={
                    "model": model, "temperature": 0, "seed": 7, "max_tokens": 1500,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"HTTP {r.status_code}"
                else:
                    r.raise_for_status()
                    out = {"content": r.json()["choices"][0]["message"]["content"] or "", "model": model}
                    CACHE.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(out))
                    return out
            except (requests.RequestException, KeyError, ValueError) as e:
                last = type(e).__name__
            sleep(2 ** attempt)
        errors.append(f"{model}: {last}")
    raise LLMUnavailable("all models unavailable (" + "; ".join(errors) + ")")
