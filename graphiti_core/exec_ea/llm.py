"""LLM client helpers for Exec-EA smoke runs."""

import os

from dotenv import load_dotenv

from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

DEFAULT_LITELLM_MODEL = 'gpt-4.1-mini'
DEFAULT_LITELLM_SMALL_MODEL = 'gpt-4.1-nano'

LITELLM_API_KEY_ENV_VARS = ('LITELLM_API_KEY', 'LITELLM_TOKEN', 'LITELLM')
LITELLM_BASE_URL_ENV_VARS = ('LITELLM_BASE_URL', 'LITELLM_PROXY_URL', 'OPENAI_BASE_URL')
LITELLM_MODEL_ENV_VARS = ('LITELLM_MODEL', 'OPENAI_MODEL', 'MODEL_NAME', 'LLM_MODEL')
LITELLM_SMALL_MODEL_ENV_VARS = ('LITELLM_SMALL_MODEL', 'OPENAI_SMALL_MODEL', 'SMALL_MODEL_NAME')


class LiteLLMEnvironmentError(RuntimeError):
    """Raised when the LiteLLM proxy environment is incomplete."""


def litellm_config_from_env(
    *,
    model: str | None = None,
    small_model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> LLMConfig:
    """Build an OpenAI-compatible LLMConfig for a LiteLLM proxy."""

    load_dotenv()

    resolved_api_key = api_key or _first_env(LITELLM_API_KEY_ENV_VARS)
    resolved_base_url = base_url or _first_env(LITELLM_BASE_URL_ENV_VARS)
    resolved_model = model or _first_env(LITELLM_MODEL_ENV_VARS) or DEFAULT_LITELLM_MODEL
    resolved_small_model = (
        small_model or _first_env(LITELLM_SMALL_MODEL_ENV_VARS) or DEFAULT_LITELLM_SMALL_MODEL
    )

    missing = []
    if not resolved_api_key:
        missing.append('/'.join(LITELLM_API_KEY_ENV_VARS))
    if not resolved_base_url:
        missing.append('/'.join(LITELLM_BASE_URL_ENV_VARS))

    if missing:
        raise LiteLLMEnvironmentError(
            'Missing LiteLLM configuration: '
            + ', '.join(missing)
            + '. Set a proxy token and base URL before running LLM smoke tests.'
        )

    return LLMConfig(
        api_key=resolved_api_key,
        base_url=resolved_base_url.rstrip('/'),
        model=resolved_model,
        small_model=resolved_small_model,
        temperature=0,
    )


def litellm_client_from_env(
    *,
    model: str | None = None,
    small_model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 4096,
) -> OpenAIGenericClient:
    """Create Graphiti's OpenAI-compatible client configured for LiteLLM."""

    return OpenAIGenericClient(
        config=litellm_config_from_env(
            model=model,
            small_model=small_model,
            base_url=base_url,
            api_key=api_key,
        ),
        max_tokens=max_tokens,
    )


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None
