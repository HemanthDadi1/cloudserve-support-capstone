"""Model access: the one place that handles retries, caching and the outage signal (FR-11).

Callers catch LLMUnavailable and escalate instead of failing. Responses are cached on disk by
(model, system, user), which saves free-tier quota and makes reruns reproducible.
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
RETRIES, TIMEOUT = 4, 60


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


def complete(system: str, user: str, sleep=time.sleep) -> str:
    key, model = os.getenv("OPENROUTER_API_KEY"), os.getenv("MODEL_NAME", "recursive/flint-v1.0:free")
    path = CACHE / f"{hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text())["content"]
    if not key:
        raise LLMUnavailable("OPENROUTER_API_KEY is not set")
    last = None
    # shortcut: no circuit breaker, so a full outage costs ~15 s of backoff per model call; add one if runs get slow.
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
                content = r.json()["choices"][0]["message"]["content"] or ""
                CACHE.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"model": model, "content": content}))
                return content
        except (requests.RequestException, KeyError, ValueError) as e:
            last = type(e).__name__
        sleep(2 ** attempt)
    raise LLMUnavailable(f"model unavailable after {RETRIES} attempts ({last})")
