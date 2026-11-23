"""Thinking switch (LLM_THINK / JUDGE_THINK) and the benchmark-chosen defaults. No LLM, no network."""

import app
import config
from llm.ollama_provider import OllamaProvider


class _Resp(dict):
    pass


class _FakeClient:
    def __init__(self):
        self.kwargs = None

    def chat(self, **kwargs):
        self.kwargs = kwargs
        return {"message": {"content": '{"x": 1}'}}


def _call(provider):
    from pydantic import BaseModel

    class S(BaseModel):
        x: int

    fake = _FakeClient()
    provider.client = fake
    assert provider.generate_structured("p", S) == {"x": 1}
    return fake.kwargs


def test_provider_sends_think_only_when_set():
    assert "think" not in _call(OllamaProvider(model="m"))
    assert _call(OllamaProvider(model="m", think=False))["think"] is False


def test_env_bool(monkeypatch):
    for raw, want in (("false", False), ("0", False), ("TRUE", True), ("yes", True)):
        monkeypatch.setenv("X_THINK", raw)
        assert config._env_bool("X_THINK", None) is want
    monkeypatch.setenv("X_THINK", "")
    assert config._env_bool("X_THINK", None) is None
    monkeypatch.delenv("X_THINK")
    assert config._env_bool("X_THINK", False) is False


def test_create_provider_passes_think():
    cfg = config.LLMConfig(provider="ollama", model="qwen3:8b")
    assert app.create_provider(cfg, think=False).think is False
    assert app.create_provider(cfg).think is None


def test_defaults_match_benchmark_choice(monkeypatch):
    for var in ("LLM_MODEL", "LLM_THINK", "JUDGE_THINK"):
        monkeypatch.delenv(var, raising=False)
    import importlib
    fresh = importlib.reload(config)
    try:
        cfg = fresh.LLMConfig()
        if not (config.Path(fresh.__file__).parent / ".env").exists():
            assert cfg.model == "qwen3:8b"
        assert cfg.think is False and cfg.judge_think is None
    finally:
        importlib.reload(config)
