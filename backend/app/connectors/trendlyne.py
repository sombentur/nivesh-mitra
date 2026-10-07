"""Trendlyne MCP — read-only market intelligence (doc 06): red flags, shareholding, events, DVM scores.

Your personal server URL contains your token, so it is treated like a password: it is stored encrypted, and every
error message is scrubbed of it before it can reach a log or the screen.

Trendlyne's terms don't allow keeping its data in a "searchable, machine-readable database" without written
permission, so results are held only briefly in memory by the callers (see docs/06 §3) — never written to the DB.
"""

import asyncio
import json
import re
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.connectors.http import SourceUnavailable

TIMEOUT_SECONDS = 45


class TrendlyneUnavailable(SourceUnavailable):
    pass


def redact(text: str) -> str:
    return re.sub(r"(token=)[^&\s'\"]+", r"\1***", text)


@dataclass
class ToolInfo:
    name: str
    description: str
    required: list[str]


async def _session_run(url: str, fn):
    async with streamable_http_client(url) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _run(url: str, fn):
    try:
        return asyncio.run(asyncio.wait_for(_session_run(url, fn), TIMEOUT_SECONDS))
    except TimeoutError as exc:
        raise TrendlyneUnavailable("Trendlyne didn't answer in time") from exc
    except TrendlyneUnavailable:
        raise
    except BaseException as exc:  # noqa: BLE001 — network, auth and protocol errors all end up here
        detail = redact("; ".join(f"{type(e).__name__}: {e}" for e in _leaves(exc)))
        if "403" in detail or "1007" in detail:
            detail = "Trendlyne refused the token (it may be wrong, expired, or the MCP plan inactive)"
        raise TrendlyneUnavailable(f"Couldn't use Trendlyne MCP — {detail}") from None


def _attr(obj, *names):
    """MCP SDK 2.x uses snake_case field names; 1.x used camelCase. Accept either."""
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return None


def _leaves(exc: BaseException) -> list[BaseException]:
    """anyio task groups nest the real error inside exception groups — dig it out."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for e in exc.exceptions for leaf in _leaves(e)]
    return [exc]


def list_tools(url: str) -> list[ToolInfo]:
    """The tools this server offers. Listing tools is not a tool call."""

    async def fn(session: ClientSession):
        res = await session.list_tools()
        return [
            ToolInfo(t.name, (t.description or "").strip().split("\n")[0][:200], list((_attr(t, "input_schema", "inputSchema") or {}).get("required", [])))
            for t in res.tools
        ]

    return _run(url, fn)


def call_tool(url: str, name: str, arguments: dict) -> dict | list | str:
    """One tool call (counts against your Trendlyne plan's daily/monthly limit)."""

    async def fn(session: ClientSession):
        res = await session.call_tool(name, arguments)
        if _attr(res, "is_error", "isError"):
            raise TrendlyneUnavailable(redact(" ".join(getattr(c, "text", "") for c in res.content))[:300] or "tool error")
        structured = _attr(res, "structured_content", "structuredContent")
        if structured:
            return structured
        text = "\n".join(getattr(c, "text", "") for c in res.content)
        try:
            return json.loads(text)
        except ValueError:
            return text

    return _run(url, fn)
