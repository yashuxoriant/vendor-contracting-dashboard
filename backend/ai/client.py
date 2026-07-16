import logging
from typing import List, Dict, Optional, Generator
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

def get_ai_client():
    from config import get_settings
    s = get_settings()
    ep = s.azure_openai_chat_endpoint
    key = s.azure_openai_api_key
    if ep and 'services.ai.azure.com' in ep and key and 'dummy' not in key:
        try:
            import anthropic
            c = anthropic.Anthropic(base_url=ep.rstrip('/'), api_key=key,
                default_headers={'x-ms-useragent': 'anthropic-azure/1.0'}, max_retries=0)
            logger.info('AI client: Azure AI Foundry (Anthropic)')
            return c, s.azure_openai_chat_deployment
        except Exception as e:
            logger.warning(f'Azure AI Foundry client failed: {e}')
    if s.anthropic_api_key and s.anthropic_api_key != 'dummy-api-key':
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=0)
            logger.info('AI client: Direct Anthropic API')
            return c, s.claude_model_default
        except Exception as e:
            logger.warning(f'Direct Anthropic client failed: {e}')
    logger.warning('AI client: None - rule-based fallback')
    return None, None


def call_ai(messages, system, model=None, max_tokens=8192, temperature=0.3):
    client, default_model = get_ai_client()
    if not client:
        return None
    use_model = model or default_model

    try:
        r = client.messages.create(model=use_model, max_tokens=max_tokens, system=system, messages=messages)
        return r.content[0].text
    except Exception as e:
        logger.error(f'AI call failed (model={use_model}): {e}')
        return None


def stream_ai(messages, system, model=None, max_tokens=8192, temperature=0.3):
    client, default_model = get_ai_client()
    if not client:
        return None
    use_model = model or default_model
    def _gen():
        try:
            with client.messages.stream(model=use_model, max_tokens=max_tokens,
                    system=system, messages=messages) as stream:
                for chunk in stream.text_stream:
                    yield chunk
        except Exception as e:
            logger.error(f'AI stream failed (model={use_model}): {e}')
            yield '__STREAM_ERROR__'
    return _gen()
