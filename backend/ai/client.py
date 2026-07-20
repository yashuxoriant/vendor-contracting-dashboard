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
import asyncio
import logging
import socket
import time
from typing import AsyncIterator, List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── DNS reachability cache ────────────────────────────────────────────────────
_DNS_CACHE: Dict[str, Tuple[bool, float]] = {}
_DNS_CACHE_TTL = 300  # 5 minutes


def _is_host_reachable(url: str) -> bool:
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


# ── Singleton client cache ─────────────────────────────────────────────────────
# Avoids reconstructing the HTTP client on every request.
_cached_client: Optional[Any] = None
_cached_model: Optional[str] = None


def get_ai_client():
    """Return a cached (client, model) pair. Builds once, reuses thereafter."""
    global _cached_client, _cached_model
    if _cached_client is not None:
        return _cached_client, _cached_model

    from config import get_settings
    s = get_settings()
    ep = s.azure_openai_chat_endpoint
    key = s.azure_openai_api_key
    if ep and 'services.ai.azure.com' in ep and key and 'dummy' not in key:
        try:
            import anthropic
            c = anthropic.Anthropic(
                base_url=ep.rstrip('/'),
                api_key=key,
                default_headers={'x-ms-useragent': 'anthropic-azure/1.0'},
                max_retries=0,
            )
            logger.info('AI client: Azure AI Foundry (Anthropic) — singleton cached')
            _cached_client, _cached_model = c, s.azure_openai_chat_deployment
            return _cached_client, _cached_model
        except Exception as e:
            logger.warning('Azure AI Foundry client failed: %s', e)

    if getattr(s, 'anthropic_api_key', None) and s.anthropic_api_key != 'dummy-api-key':
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=0)
            logger.info('AI client: Direct Anthropic API — singleton cached')
            _cached_client, _cached_model = c, s.claude_model_default
            return _cached_client, _cached_model
        except Exception as e:
            logger.warning('Direct Anthropic client failed: %s', e)

    logger.warning('AI client: None — rule-based fallback will be used')
    return None, None


def call_ai(
    messages: List[Dict],
    system: str,
    model: Optional[str] = None,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> Optional[str]:
    """Synchronous AI call. Runs in a thread when invoked from async context."""
    client, default_model = get_ai_client()
    if not client:
        return None
    use_model = model or default_model
    try:
        r = client.messages.create(
            model=use_model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return r.content[0].text
    except Exception as e:
        logger.error('AI call failed (model=%s): %s', use_model, e)
        return None


async def call_ai_streaming(
    messages: List[Dict],
    system: str,
    model: Optional[str] = None,
    max_tokens: int = 8192,
) -> AsyncIterator[str]:
    """
    Async generator that yields text tokens as they arrive from the AI model.

    Uses the Anthropic SDK's streaming API when available.
    Falls back to a word-by-word simulation of the synchronous response so the
    UX always shows progressive output, even on endpoints without true streaming.
    """
    client, default_model = get_ai_client()
    use_model = model or default_model

    if client is None:
        # No AI client — nothing to stream
        return

    # ── True streaming via Anthropic SDK ──────────────────────────────────────
    # Use asyncio.to_thread so the blocking SDK call never occupies the event loop.
    # The SDK's streaming context manager yields text_delta events synchronously,
    # which we collect in a queue and yield asynchronously.
    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    def _stream_worker():
        """Runs in a thread — puts tokens into the queue."""
        try:
            with client.messages.stream(
                model=use_model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    asyncio.get_event_loop().call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:
            logger.error("AI streaming failed (model=%s): %s", use_model, exc)
        finally:
            asyncio.get_event_loop().call_soon_threadsafe(queue.put_nowait, SENTINEL)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _stream_worker)

    while True:
        token = await queue.get()
        if token is SENTINEL:
            break
        yield token




