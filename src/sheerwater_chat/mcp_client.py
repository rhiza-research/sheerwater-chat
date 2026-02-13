"""MCP client for connecting to sheerwater-mcp server."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool

logger = logging.getLogger(__name__)

MAX_CONNECT_RETRIES = 10
RETRY_DELAY = 2  # seconds
MAX_CALL_RETRIES = 3


class McpClient:
    """Client for connecting to an MCP server via SSE with automatic reconnection."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []
        self._lock = asyncio.Lock()
        self._connected = False

    @asynccontextmanager
    async def connection(self):
        """Context manager for MCP connection with retry logic (legacy method for lifespan)."""
        await self._connect()
        try:
            yield self
        finally:
            pass  # Keep connection alive across app lifetime

    async def _connect(self):
        """Establish connection to MCP server."""
        async with self._lock:
            if self._connected and self._session:
                return  # Already connected

            for attempt in range(MAX_CONNECT_RETRIES):
                try:
                    logger.info(f"Connecting to MCP server at {self.server_url} (attempt {attempt + 1}/{MAX_CONNECT_RETRIES})")

                    # Store connection context
                    self._sse_context = sse_client(self.server_url)
                    read_stream, write_stream = await self._sse_context.__aenter__()

                    self._session_context = ClientSession(read_stream, write_stream)
                    session = await self._session_context.__aenter__()

                    await session.initialize()
                    self._session = session

                    # Fetch available tools
                    tools_result = await session.list_tools()
                    self._tools = tools_result.tools
                    self._connected = True
                    logger.info(f"Connected to MCP server, found {len(self._tools)} tools")
                    return

                except httpx.ConnectError as e:
                    if attempt < MAX_CONNECT_RETRIES - 1:
                        logger.warning(f"MCP server not ready, retrying in {RETRY_DELAY}s: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.error(f"Failed to connect to MCP server after {MAX_CONNECT_RETRIES} attempts")
                        raise

    async def _reconnect(self):
        """Reconnect to MCP server after connection loss."""
        logger.warning("Attempting to reconnect to MCP server...")
        async with self._lock:
            # Clean up old connection
            if self._session:
                try:
                    await self._session_context.__aexit__(None, None, None)
                except Exception:
                    pass
                try:
                    await self._sse_context.__aexit__(None, None, None)
                except Exception:
                    pass

            self._session = None
            self._connected = False
            self._tools = []

        # Establish new connection
        await self._connect()

    async def list_tools(self) -> list[Tool]:
        """Get available tools from the MCP server."""
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server with automatic reconnection."""
        for attempt in range(MAX_CALL_RETRIES):
            if not self._connected or not self._session:
                logger.warning("MCP not connected, attempting to connect...")
                await self._connect()

            try:
                logger.info(f"Calling MCP tool: {name} with arguments: {arguments}")
                result = await self._session.call_tool(name, arguments)
                logger.info(f"Tool {name} returned successfully")
                return result

            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, EOFError, ConnectionError) as e:
                logger.error(f"MCP connection error during tool call (attempt {attempt + 1}/{MAX_CALL_RETRIES}): {e}")

                if attempt < MAX_CALL_RETRIES - 1:
                    await self._reconnect()
                    await asyncio.sleep(1)  # Brief delay before retry
                else:
                    raise RuntimeError(f"Failed to call tool {name} after {MAX_CALL_RETRIES} attempts") from e

    def get_tools_for_claude(self) -> list[dict]:
        """Convert MCP tools to Claude API tool format."""
        claude_tools = []
        for tool in self._tools:
            claude_tool = {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            claude_tools.append(claude_tool)
        return claude_tools
