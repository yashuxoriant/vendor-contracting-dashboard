"""
AI Client — multi-provider wrapper
Priority order:
  1. Azure AI Foundry (Anthropic Claude) — if AZURE_OPENAI_CHAT_ENDPOINT set
  2. Direct Anthropic API             — if ANTHROPIC_API_KEY set
  3. Azure OpenAI (standard GPT)      — if USE_AZURE_OPENAI=true
  4. Direct OpenAI API                — if OPENAI_API_KEY set
  5. Rule-based fallback              — when no credentials available
"""
import logging
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── Provider type tag passed alongside client so call_ai knows how to invoke ──
# "anthropic" → client.messages.create(system=..., messages=...)
# "openai"    → client.chat.completions.create(messages=[{"role":"system",...}, ...])
_ClientPair = Tuple[Optional[Any], Optional[str], str]   # (client, model, provider_type)


def get_ai_client() -> _ClientPair:
    """
    Return (client, model_name, provider_type) for the first available provider.
    Returns (None, None, "none") when no credentials are configured → triggers rule-based.
    """
    from config import get_settings
    settings = get_settings()

    # ── 1. Azure AI Foundry Anthropic proxy ──────────────────────────────────
    endpoint = settings.azure_openai_chat_endpoint
    api_key  = settings.azure_openai_api_key
    if endpoint and "services.ai.azure.com" in endpoint and api_key and "dummy" not in api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(
                base_url=endpoint.rstrip("/"),
                api_key=api_key,
                default_headers={"x-ms-useragent": "anthropic-azure/1.0"},
                max_retries=0,
                timeout=15.0,
            )
            logger.info("AI client: Azure AI Foundry (Anthropic)")
            return client, settings.azure_openai_chat_deployment, "anthropic"
        except Exception as e:
            logger.warning(f"Azure AI Foundry Anthropic client failed: {e}")

    # ── 2. Direct Anthropic API ───────────────────────────────────────────────
    if settings.anthropic_api_key and settings.anthropic_api_key != "dummy-api-key":
        try:
            import anthropic
            client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key,
                max_retries=0,
                timeout=15.0,
            )
            logger.info("AI client: Direct Anthropic API")
            return client, settings.claude_model_default, "anthropic"
        except Exception as e:
            logger.warning(f"Direct Anthropic client failed: {e}")

    # ── 3. Azure OpenAI (standard openai SDK) ────────────────────────────────
    if settings.use_azure_openai:
        az_endpoint = settings.azure_openai_endpoint
        az_key      = settings.azure_openai_api_key
        az_deploy   = settings.azure_openai_chat_deployment
        if (az_endpoint and "dummy" not in az_endpoint
                and az_key and "dummy" not in az_key):
            try:
                from openai import AzureOpenAI
                client = AzureOpenAI(
                    azure_endpoint=az_endpoint,
                    api_key=az_key,
                    api_version=settings.azure_openai_api_version,
                    max_retries=0,
                    timeout=15.0,
                )
                logger.info("AI client: Azure OpenAI (GPT)")
                return client, az_deploy, "openai"
            except Exception as e:
                logger.warning(f"Azure OpenAI client failed: {e}")

    # ── 4. Direct OpenAI API ─────────────────────────────────────────────────
    if settings.openai_api_key and settings.openai_api_key != "dummy-openai-key":
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.openai_api_key,
                max_retries=0,
                timeout=15.0,
            )
            logger.info("AI client: Direct OpenAI API")
            return client, settings.openai_model_default, "openai"
        except Exception as e:
            logger.warning(f"Direct OpenAI client failed: {e}")

    logger.warning("AI client: None — rule-based fallback will be used")
    return None, None, "none"


def call_ai(
    messages: List[Dict],
    system: str,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Optional[str]:
    """
    Call the AI model with messages + system prompt.
    Works with both Anthropic and OpenAI SDK interfaces.
    Returns response text or None on failure (triggers rule-based fallback).
    """
    client, default_model, provider = get_ai_client()
    if not client:
        return None

    use_model = model or default_model

    try:
        if provider == "anthropic":
            response = client.messages.create(
                model=use_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )
            return response.content[0].text

        elif provider == "openai":
            # Prepend system message for OpenAI-style API
            openai_messages = [{"role": "system", "content": system}] + messages
            response = client.chat.completions.create(
                model=use_model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=openai_messages,
            )
            return response.choices[0].message.content

        else:
            return None

    except Exception as e:
        logger.error(f"AI call failed (provider={provider}, model={use_model}): {e}")
        return None
