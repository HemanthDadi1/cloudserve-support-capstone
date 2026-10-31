"""Model access: the one place that handles retries, fallbacks, caching and the outage signal (FR-11).

Models are tried in order (MODEL_NAME, then MODEL_FALLBACKS). A busy or failing model is skipped at once;
only when every model is busy does the client wait and make one more pass. Callers catch LLMUnavailable
and escalate instead of failing. Responses are cached on disk by (model list, system, user), which saves
free-tier quota and makes reruns reproducible.
Models named "groq:<model>" go to Groq (GROQ_API_KEY); all others to OpenRouter (OPENROUTER_API_KEY).
Once a provider reports its daily cap, the rest of the run skips that provider.
Order history (31 Oct): Flint was down all day; OpenRouter's account-wide cap of 50 free requests a day then
ran out mid-test; Groq models answered the same five test tickets in 0.3-2 s with all sentences grounded.
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
PROVIDERS = {"openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
             "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY")}
EXHAUSTED: dict[str, str] = {}  # provider -> why it is unusable for the rest of this process
# Each model is tried once per pass; when every model is busy, wait (retry-after, capped) and pass again.
# Groq free tier: 1,000 requests/day but 8,000 tokens/minute per model, i.e. ~3 calls/minute each.
PASSES, TIMEOUT, MAX_WAIT = 2, 60, 60
DEFAULT_MODEL = "groq:qwen/qwen3.8-27b"
DEFAULT_FALLBACKS = ("groq:openai/gpt-oss-120b,groq:openai/gpt-oss-20b,nvidia/nemotron-3.5-super-vl:free,"
                     "recursive/flint-v1.0:free,xingchen-agi/xing4.0-29b-a4b:free")


def provider(model: str) -> tuple[str, str]:
    return ("groq", model.removeprefix("groq:")) if model.startswith("groq:") else ("openrouter", model)


def models() -> list[str]:
    fallbacks = [m.strip() for m in os.getenv("MODEL_FALLBACKS", DEFAULT_FALLBACKS).split(",") if m.strip()]
    return [os.getenv("MODEL_NAME", DEFAULT_MODEL)] + fallbacks


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
    chain = models()
    path = CACHE / f"{hashlib.sha256(json.dumps([chain, system, user]).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text())
    errors = {}
    for p in range(PASSES):
        wait = 2.0
        for model in chain:
            prov, name = provider(model)
            url, key_var = PROVIDERS[prov]
            key = os.getenv(key_var)
            if not key or prov in EXHAUSTED:
                errors[model] = EXHAUSTED.get(prov) or f"{key_var} not set"
                continue
            try:
                r = requests.post(url, timeout=TIMEOUT, headers={"Authorization": f"Bearer {key}"}, json={
                    "model": name, "temperature": 0, "seed": 7, "max_tokens": 1500,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                if r.status_code == 429 and re.search(r"per[- ]day", r.text):  # OpenRouter / Groq wording
                    errors[model] = EXHAUSTED[prov] = "daily cap reached"
                    continue
                if r.status_code in (401, 403):  # missing or placeholder key: no other model there will work
                    errors[model] = EXHAUSTED[prov] = f"{key_var} rejected (HTTP {r.status_code})"
                    continue
                if r.status_code == 429 or r.status_code >= 500:  # busy or down: move on to the next model
                    errors[model] = f"HTTP {r.status_code}"
                    try:
                        wait = max(wait, float(r.headers.get("retry-after", 0)))
                    except ValueError:
                        pass
                    continue
                r.raise_for_status()
                out = {"content": r.json()["choices"][0]["message"]["content"] or "", "model": model}
                CACHE.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(out))
                return out
            except (requests.RequestException, KeyError, ValueError) as e:
                errors[model] = type(e).__name__
        usable = [m for m in chain if os.getenv(PROVIDERS[provider(m)[0]][1]) and provider(m)[0] not in EXHAUSTED]
        if p < PASSES - 1 and usable:
            sleep(min(wait, MAX_WAIT))
    raise LLMUnavailable("all models unavailable (" + "; ".join(f"{m}: {e}" for m, e in errors.items()) + ")")
