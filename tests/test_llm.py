import pytest
import requests

from src import llm


class Resp:
    def __init__(self, status, content="{}", text="", headers=None):
        self.status_code, self.content, self.text, self.headers = status, content, text, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "EXHAUSTED", {})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("MODEL_NAME", "primary")
    monkeypatch.setenv("MODEL_FALLBACKS", "backup1,backup2")
    calls = []

    def use(*responses):
        it = iter(responses)

        def post(url, *a, json, headers, **kw):
            calls.append(json["model"] if "openrouter" in url else f"groq:{json['model']}:{headers['Authorization']}")
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(llm.requests, "post", post)
        return calls
    return use


def test_busy_model_is_skipped_at_once_and_result_cached(offline):
    calls = offline(Resp(503), requests.Timeout(), Resp(200, '{"ok": 1}'))
    assert llm.complete("s", "u", sleep=pytest.fail) == {"content": '{"ok": 1}', "model": "backup2"}
    assert llm.complete("s", "u", sleep=pytest.fail)["model"] == "backup2"  # second call served from cache
    assert calls == ["primary", "backup1", "backup2"]


def test_waits_retry_after_only_when_every_model_is_busy(offline):
    waits = []
    busy = Resp(429, headers={"retry-after": "7"})
    calls = offline(busy, busy, busy, Resp(200, '{"ok": 2}'))
    assert llm.complete("s", "u2", sleep=waits.append)["model"] == "primary"
    assert waits == [7.0] and calls == ["primary", "backup1", "backup2", "primary"]


def test_gives_up_with_clear_signal(offline):
    offline(*[Resp(503)] * 6)
    with pytest.raises(llm.LLMUnavailable, match="backup2: HTTP 503"):
        llm.complete("s", "u3", sleep=lambda s: None)


def test_groq_models_use_groq_endpoint_and_key(offline, monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "groq:llama-test")
    calls = offline(Resp(200, '{"ok": 3}'))
    assert llm.complete("s", "u5", sleep=pytest.fail)["model"] == "groq:llama-test"
    assert calls == ["groq:llama-test:Bearer groq-key"]


def test_daily_cap_skips_the_provider_for_the_rest_of_the_run(offline, monkeypatch):
    monkeypatch.setenv("MODEL_FALLBACKS", "backup1,groq:llama-test")
    capped = Resp(429, text='{"error":{"message":"Rate limit exceeded: free-models-per-day"}}')
    calls = offline(capped, Resp(200, '{"ok": 4}'), Resp(200, '{"ok": 5}'))
    assert llm.complete("s", "u6", sleep=pytest.fail)["model"] == "groq:llama-test"
    assert llm.complete("s", "u7", sleep=pytest.fail)["model"] == "groq:llama-test"
    assert calls[0] == "primary" and all(c.startswith("groq:") for c in calls[1:])  # backup1 never tried


def test_rejected_key_disables_the_provider_without_waiting(offline, monkeypatch):
    monkeypatch.setenv("MODEL_FALLBACKS", "backup1,groq:llama-test")
    calls = offline(Resp(401), Resp(401))  # OpenRouter placeholder key, then Groq placeholder key
    with pytest.raises(llm.LLMUnavailable, match="GROQ_API_KEY rejected"):
        llm.complete("s", "u8", sleep=pytest.fail)
    assert calls == ["primary", "groq:llama-test:Bearer groq-key"]  # backup1 skipped, no second pass


def test_missing_key_is_unavailable_not_a_crash(offline, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete("s", "u4")


def test_prompt_files_load_and_render():
    p = llm.load_prompt("PR-01_answer.txt")
    assert p["id"] == "PR-01" and "{ticket}" in p["user"]
    assert "hello" in llm.render(p["user"], ticket="hello", passages="")
