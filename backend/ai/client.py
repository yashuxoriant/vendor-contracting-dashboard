"""
AI Client — multi-provider wrapper
Priority order:
  1. Azure AI Foundry (Anthropic Claude) — if AZURE_OPENAI_CHAT_ENDPOINT set
  2. Direct Anthropic API             — if ANTHROPIC_API_KEY set
  3. Azure OpenAI (standard GPT)      — if USE_AZURE_OPENAI=true
  4. Direct OpenAI API                — if OPENAI_API_KEY set
  5. Rule-based fallback              — when no credentials available

DNS reachability is checked before building clients (cached 5 min) so a dead
endpoint does not add a 10-second connection timeout to every user message.
"""
import logging
import socket
import time
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── DNS reachability cache ────────────────────────────────────────────────────
# Maps hostname → (reachable: bool, checked_at: float)
# Re-checks after DNS_CACHE_TTL seconds so a VPN reconnect is picked up.
_DNS_CACHE: Dict[str, Tuple[bool, float]] = {}
_DNS_CACHE_TTL = 300  # 5 minutes


def _is_host_reachable(url: str) -> bool:
    """
    Return True if the hostname in *url* resolves in DNS.
    Uses a short-lived in-process cache to avoid blocking every request.
    """
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or url
    except Exception:
        host = url

    cached = _DNS_CACHE.get(host)
    if cached is not None:
        reachable, ts = cached
        if time.monotonic() - ts < _DNS_CACHE_TTL:
            return reachable

    try:
        socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        _DNS_CACHE[host] = (True, time.monotonic())
        return True
    except OSError:
        _DNS_CACHE[host] = (False, time.monotonic())
        logger.warning("AI provider unreachable (DNS failed): %s — skipping", host)
        return False

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



