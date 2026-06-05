import pytest

from graphiti_core.exec_ea import (
    DEFAULT_LITELLM_MODEL,
    DEFAULT_LITELLM_SMALL_MODEL,
    LiteLLMEnvironmentError,
    litellm_client_from_env,
    litellm_config_from_env,
)
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient


def test_litellm_config_from_env_uses_existing_litellm_token_name(monkeypatch) -> None:
    monkeypatch.setenv('LITELLM', 'token')
    monkeypatch.setenv('LITELLM_BASE_URL', 'http://127.0.0.1:4000/')

    config = litellm_config_from_env()

    assert config.api_key == 'token'
    assert config.base_url == 'http://127.0.0.1:4000'
    assert config.model == DEFAULT_LITELLM_MODEL
    assert config.small_model == DEFAULT_LITELLM_SMALL_MODEL
    assert config.temperature == 0


def test_litellm_config_from_env_allows_model_override(monkeypatch) -> None:
    monkeypatch.setenv('LITELLM_API_KEY', 'token')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://litellm.example/v1')
    monkeypatch.setenv('LITELLM_MODEL', 'openai/codex-mini')
    monkeypatch.setenv('LITELLM_SMALL_MODEL', 'openai/codex-mini-low')

    config = litellm_config_from_env()

    assert config.model == 'openai/codex-mini'
    assert config.small_model == 'openai/codex-mini-low'


def test_litellm_config_from_env_requires_base_url(monkeypatch) -> None:
    monkeypatch.setenv('LITELLM', 'token')
    monkeypatch.delenv('LITELLM_BASE_URL', raising=False)
    monkeypatch.delenv('LITELLM_PROXY_URL', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)

    with pytest.raises(LiteLLMEnvironmentError, match='base URL'):
        litellm_config_from_env()


def test_litellm_client_from_env_uses_graphiti_openai_compatible_client(monkeypatch) -> None:
    monkeypatch.setenv('LITELLM', 'token')
    monkeypatch.setenv('LITELLM_BASE_URL', 'http://127.0.0.1:4000')

    client = litellm_client_from_env(model='gpt-4.1-mini')

    assert isinstance(client, OpenAIGenericClient)
    assert client.model == 'gpt-4.1-mini'
