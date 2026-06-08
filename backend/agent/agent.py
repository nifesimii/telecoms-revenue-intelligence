"""Claude conversation loop. Handles tool calls. No SQL here.

The agent owns one job: drive a single turn of conversation with Claude,
running any tool calls that come back, until Claude returns a final text
response. It does not know about SQL, Presto, or sample data — those live
behind :mod:`backend.agent.tool_executor`. It does not author the system
prompt — that lives in :mod:`backend.agent.prompts`. It does not know the
tool definitions — those live in :mod:`backend.agent.tools`.

Public surface:
    * :func:`run_agent` — single async entry point.

A bottom-of-file ``if __name__ == "__main__":`` smoke test exercises the
loop end-to-end against the sample CSVs.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import anthropic

from backend import config
from backend.agent import prompts, tool_executor
from backend.agent.tools import TOOLS

logger = logging.getLogger(__name__)

# --- Model config ---
MODEL_NAME = "claude-sonnet-4-5"
MAX_TOKENS = 2048
MAX_TOOL_ITERATIONS = 5  # safety cap — protects against pathological loops

# --- Rate-limit retry ---
# When Anthropic returns 429 (RateLimitError), retry up to
# RATE_LIMIT_MAX_RETRIES times with a fixed RATE_LIMIT_RETRY_DELAY_SECONDS
# wait between attempts. If every retry also rate-limits, the final
# RateLimitError propagates and the standard ``except Exception`` path in
# run_agent returns FALLBACK_RESPONSE — no exception escapes to the caller.
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_RETRY_DELAY_SECONDS = 20

# --- User-facing fallback ---
FALLBACK_RESPONSE = (
    "I encountered an error retrieving that data. Please try again."
)


async def run_agent(
    user_message: str,
    conversation_history: list = [],
) -> dict:
    """Drive one user turn through Claude with a tool-use loop.

    Args:
        user_message: The latest user message text.
        conversation_history: Prior turns, each a ``{"role": ..., "content":
            ...}`` dict in the format Anthropic's Messages API expects. The
            caller's list is never mutated — it's copied on entry.

    Returns:
        A dict with three keys:
            * ``response`` — the final assistant text Claude produced
            * ``tools_called`` — ordered list of tool names invoked this turn
              (duplicates preserved)
            * ``raw_data`` — ``{tool_name: parsed_result_envelope}``. If the
              same tool is called more than once in one turn, the latest
              call wins.

        On any API failure with no prior text accumulated, returns
        :data:`FALLBACK_RESPONSE` with empty ``tools_called`` and
        ``raw_data``.
    """
    # Defensive copy — never mutate the caller's history list, and avoid the
    # mutable-default trap on conversation_history=[].
    messages: list[dict[str, Any]] = list(conversation_history)
    messages.append({"role": "user", "content": user_message})

    tools_called: list[str] = []
    raw_data: dict[str, Any] = {}
    last_text: str = ""

    try:
        client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    except Exception:
        logger.exception("Failed to construct Anthropic client")
        return _error_response()

    system_prompt = prompts.get_system_prompt()

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await _create_with_rate_limit_retry(
                client,
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )
        except Exception:
            logger.exception(
                "Claude API call failed on iteration %d", iteration + 1
            )
            # If we already produced some text in an earlier iteration, return
            # it rather than the generic fallback.
            if last_text:
                return {
                    "response": last_text,
                    "tools_called": tools_called,
                    "raw_data": raw_data,
                }
            return _error_response()

        # Capture any text Claude produced in this round, so we have something
        # to return even if we later hit the iteration cap or an error.
        text_pieces = [
            block.text for block in response.content if block.type == "text"
        ]
        if text_pieces:
            last_text = "\n".join(text_pieces).strip()

        # Pull out tool_use blocks. If none, Claude is done.
        tool_use_blocks = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_use_blocks:
            return {
                "response": last_text,
                "tools_called": tools_called,
                "raw_data": raw_data,
            }

        # Append assistant turn (text + tool_use blocks) to the message list.
        messages.append(
            {
                "role": "assistant",
                "content": [_block_to_dict(b) for b in response.content],
            }
        )

        # Run each tool and collect tool_result blocks for the next user turn.
        tool_result_blocks: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            tool_input = dict(block.input or {})
            logger.info(
                "Tool call iter=%d name=%s input=%s",
                iteration + 1,
                block.name,
                tool_input,
            )

            result_block = tool_executor.execute_tool(
                {
                    "id": block.id,
                    "name": block.name,
                    "input": tool_input,
                }
            )
            tool_result_blocks.append(result_block)
            tools_called.append(block.name)

            # Populate raw_data with the parsed envelope. tool_executor
            # always returns ``content`` as a JSON string on success; on
            # error it's a human-readable string — fall back gracefully.
            content = result_block.get("content", "")
            try:
                raw_data[block.name] = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                raw_data[block.name] = {
                    "raw": content,
                    "is_error": bool(result_block.get("is_error")),
                }

        # Feed tool results back as a user turn — required by the API.
        messages.append({"role": "user", "content": tool_result_blocks})

    # Hit the iteration cap without Claude returning a clean final response.
    logger.warning(
        "Hit MAX_TOOL_ITERATIONS=%d without end_turn — returning last text",
        MAX_TOOL_ITERATIONS,
    )
    return {
        "response": last_text
        or "I was unable to complete the analysis within the allotted tool iterations.",
        "tools_called": tools_called,
        "raw_data": raw_data,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Serialise an Anthropic ContentBlock pydantic model to plain dict."""
    if hasattr(block, "model_dump"):
        return block.model_dump()
    if hasattr(block, "dict"):
        return block.dict()
    return dict(block)


def _error_response() -> dict[str, Any]:
    return {
        "response": FALLBACK_RESPONSE,
        "tools_called": [],
        "raw_data": {},
    }


async def _create_with_rate_limit_retry(client: Any, **kwargs: Any) -> Any:
    """Call ``client.messages.create`` with retry-on-rate-limit semantics.

    On :class:`anthropic.RateLimitError`, sleeps for
    ``RATE_LIMIT_RETRY_DELAY_SECONDS`` and retries up to
    ``RATE_LIMIT_MAX_RETRIES`` times. Other exceptions propagate immediately
    (the existing ``except Exception`` in :func:`run_agent` turns them into
    :data:`FALLBACK_RESPONSE`). If every retry also rate-limits, the final
    ``RateLimitError`` propagates so the same fallback path triggers — the
    caller never sees an exception.
    """
    attempt = 0
    while True:
        try:
            return await client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            attempt += 1
            if attempt > RATE_LIMIT_MAX_RETRIES:
                logger.error(
                    "Rate-limited by Anthropic — exhausted %d retries; "
                    "giving up and falling back",
                    RATE_LIMIT_MAX_RETRIES,
                )
                raise
            logger.warning(
                "Rate-limited by Anthropic; retry %d/%d in %ds",
                attempt,
                RATE_LIMIT_MAX_RETRIES,
                RATE_LIMIT_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(RATE_LIMIT_RETRY_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# Inline smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Windows default stdout is cp1252, which cannot encode the Naira symbol
    # (U+20A6). Force UTF-8 so the smoke-test print() calls don't crash.
    # Only runs in CLI mode — the FastAPI process is unaffected.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async def _smoke() -> None:
        question = "Summarise dealer commissions for 202603"
        print(f"USER QUESTION: {question}\n")
        result = await run_agent(question)
        print("=" * 70)
        print("RESPONSE:")
        print("=" * 70)
        print(result["response"])
        print()
        print("=" * 70)
        print(f"TOOLS CALLED  : {result['tools_called']}")
        print(f"RAW DATA KEYS : {list(result['raw_data'].keys())}")
        for name, payload in result["raw_data"].items():
            if isinstance(payload, dict) and "row_count" in payload:
                print(f"  {name}: row_count={payload['row_count']}")

    asyncio.run(_smoke())
