"""
framework/agents/llm_client.py — Async LLM wrapper with streaming support.

Provides:
  astream_llm(messages, system, *, model, max_tokens, temperature)
    → AsyncGenerator[str, None]
    Yields text chunks as they arrive from the LLM.
    Falls back to a single-chunk yield if the provider does not support streaming.

  acall_llm(messages, system, *, model, max_tokens, temperature)
    → str | None
    Non-streaming async wrapper — awaitable version of call_ai().

Design:
  - Reuses the provider selection logic from backend/ai/client.py (get_ai_client)
    via a deferred import — no duplication.
  - Runs the blocking Anthropic SDK in an executor so the FastAPI event loop
    is never blocked during streaming.
  - Falls back gracefully: if no LLM client is available, yields a single
    empty string and logs a warning.
  - This module must NOT import from `app/`.

OWASP: no user content is interpolated here; messages and system are passed
opaquely from the caller.
"""

from __future__ import annotations

import asyncio
import logging
import queue as _queue
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# Sentinel used to signal end-of-stream from the producer thread
_SENTINEL = object()
_STREAM_ERROR_TOKEN = "__STREAM_ERROR__"


# ---------------------------------------------------------------------------
# Internal: get client via existing backend/ai/client.py
# ---------------------------------------------------------------------------

def _get_client_and_model():
    """
    Deferred import from backend/ai/client.py so this module works both when
    called from within backend/ (existing path) and from framework/ (new path).
    Returns (anthropic_client, model_str) or (None, None).
    """
    try:
        from ai.client import get_ai_client  # noqa: PLC0415
        return get_ai_client()
    except ImportError:
        pass

    # When called from framework/ (project root on sys.path but backend/ not),
    # add backend/ explicitly so `ai.client` resolves correctly.
    import os, sys  # noqa: E401
    _backend = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "backend",
    )
    if _backend not in sys.path:
        sys.path.insert(0, _backend)
    try:
        from ai.client import get_ai_client  # noqa: PLC0415
        return get_ai_client()
    except ImportError:
        logger.warning("llm_client: backend/ai/client.py not importable; no LLM available")
        return None, None


# ---------------------------------------------------------------------------
# Async streaming generator
# ---------------------------------------------------------------------------


async def astream_llm(
    messages: list[dict],
    system: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields text chunks from the LLM as they arrive.

    Uses run_in_executor to push the blocking Anthropic SDK .stream() call
    into a thread pool, relaying chunks back to the async caller via a queue.

    Yields
    ------
    str
        Individual text tokens/chunks as produced by the LLM.
        The final chunk before StopAsyncIteration is guaranteed to be non-empty
        unless the LLM returned nothing (in which case a single empty string
        is yielded and a warning is logged).

    Example
    -------
    ::

        from framework.agents.llm_client import astream_llm

        async for chunk in astream_llm(messages, system):
            await websocket.send_text(chunk)
    """
    client, default_model = _get_client_and_model()
    use_model = model or default_model

    if client is None or use_model is None:
        logger.warning("astream_llm: no LLM client available — yielding empty")
        yield ""
        return

    chunk_queue: _queue.Queue = _queue.Queue()
    loop = asyncio.get_event_loop()

    def _produce() -> None:
        """Blocking producer: calls Anthropic SDK and puts text into the queue."""
        try:
            # Use non-streaming create() — compatible with Azure AI Foundry.
            # Streaming via .stream() can fail on Azure endpoints.
            r = client.messages.create(
                model=use_model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            chunk_queue.put(r.content[0].text)
        except Exception as exc:
            logger.error(
                "astream_llm producer error (model=%s): %s",
                use_model, exc, exc_info=True,
            )
            chunk_queue.put(_STREAM_ERROR_TOKEN)
        finally:
            chunk_queue.put(_SENTINEL)

    # Start the blocking producer in a thread pool
    loop.run_in_executor(None, _produce)

    # Drain the queue asynchronously
    had_error = False
    while True:
        # Poll without blocking the event loop
        try:
            item = chunk_queue.get_nowait()
        except _queue.Empty:
            await asyncio.sleep(0.005)
            continue

        if item is _SENTINEL:
            break
        if item == _STREAM_ERROR_TOKEN:
            had_error = True
            break
        yield item  # type: ignore[misc]

    if had_error:
        logger.warning("astream_llm: stream ended with error")


# ---------------------------------------------------------------------------
# Async non-streaming call (awaitable)
# ---------------------------------------------------------------------------


async def acall_llm(
    messages: list[dict],
    system: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> Optional[str]:
    """
    Awaitable non-streaming LLM call.

    Collects all chunks from astream_llm into a single string.
    Returns None if the LLM client is unavailable or the call fails.

    Example
    -------
    ::

        from framework.agents.llm_client import acall_llm

        text = await acall_llm(messages, system)
        if text is None:
            # fallback to rule-based response
    """
    parts: list[str] = []
    async for chunk in astream_llm(
        messages, system, model=model, max_tokens=max_tokens, temperature=temperature
    ):
        parts.append(chunk)
    result = "".join(parts).strip()
    return result if result else None
