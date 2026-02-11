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

MAX_RETRIES = 10
RETRY_DELAY = 2  # seconds


class McpClient:
    """Client for connecting to an MCP server via SSE."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []

    @asynccontextmanager
    async def connection(self):
        """Context manager for MCP connection with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Connecting to MCP server at {self.server_url} (attempt {attempt + 1}/{MAX_RETRIES})")
                async with sse_client(self.server_url) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        self._session = session

                        # Fetch available tools
                        tools_result = await session.list_tools()
                        self._tools = tools_result.tools
                        logger.info(f"Connected to MCP server, found {len(self._tools)} tools")

                        yield self

                        self._session = None
                        self._tools = []
                        return
            except httpx.ConnectError as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"MCP server not ready, retrying in {RETRY_DELAY}s: {e}")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to connect to MCP server after {MAX_RETRIES} attempts")
                    raise

    async def list_tools(self) -> list[Tool]:
        """Get available tools from the MCP server."""
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        if not self._session:
            raise RuntimeError("MCP client not connected. Use 'async with mcp_client.connection()' first.")

        logger.info(f"Calling MCP tool: {name} with arguments: {arguments}")
        result = await self._session.call_tool(name, arguments)
        logger.info(f"Tool {name} returned: {result}")
        return result

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
