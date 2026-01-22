"""MCP client for connecting to sheerwater-mcp server."""

import asyncio
import logging
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool

logger = logging.getLogger(__name__)


class McpClient:
    """Client for connecting to an MCP server via SSE."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []
        self._read_stream = None
        self._write_stream = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Connect to the MCP server."""
        async with self._lock:
            if self._session is not None:
                return

            logger.info(f"Connecting to MCP server at {self.server_url}")
            self._read_stream, self._write_stream = await sse_client(self.server_url).__aenter__()
            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            # Fetch available tools
            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools
            logger.info(f"Connected to MCP server, found {len(self._tools)} tools")

    async def disconnect(self):
        """Disconnect from the MCP server."""
        async with self._lock:
            if self._session:
                await self._session.__aexit__(None, None, None)
                self._session = None
            self._tools = []

    async def list_tools(self) -> list[Tool]:
        """Get available tools from the MCP server."""
        if not self._session:
            await self.connect()
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        if not self._session:
            await self.connect()

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
