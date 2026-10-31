import pytest
import requests

from src import llm


class Resp:
    def __init__(self, status, content="{}"):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_NAME", "primary")
    monkeypatch.setenv("MODEL_FALLBACKS", "backup1,backup2")
    calls = []

    def use(*responses):
        it = iter(responses)

        def post(*a, json, **kw):
            calls.append(json["model"])
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(llm.requests, "post", post)
        return calls
    return use


def test_retry_then_success_and_cache(offline):
    calls = offline(Resp(503), Resp(200, '{"ok": 1}'))
    assert llm.complete("s", "u", sleep=lambda s: None) == {"content": '{"ok": 1}', "model": "primary"}
    assert llm.complete("s", "u", sleep=lambda s: None)["model"] == "primary"  # second call served from cache
    assert calls == ["primary", "primary"]


def test_falls_back_when_primary_is_down(offline):
    calls = offline(Resp(503), requests.Timeout(), Resp(429), Resp(200, '{"ok": 2}'))
    assert llm.complete("s", "u2", sleep=lambda s: None)["model"] == "backup1"
    assert calls == ["primary", "primary", "backup1", "backup1"]


def test_gives_up_with_clear_signal(offline):
    offline(*[Resp(503)] * 6)
    with pytest.raises(llm.LLMUnavailable, match="backup2: HTTP 503"):
        llm.complete("s", "u3", sleep=lambda s: None)


def test_missing_key_is_unavailable_not_a_crash(offline, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete("s", "u4")


def test_prompt_files_load_and_render():
    p = llm.load_prompt("PR-01_answer.txt")
    assert p["id"] == "PR-01" and "{ticket}" in p["user"]
    assert "hello" in llm.render(p["user"], ticket="hello", passages="")
