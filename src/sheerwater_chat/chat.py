"""Chat logic with Claude API and MCP tools."""

import logging
from collections.abc import Callable
from typing import Any

import anthropic

from .mcp_client import McpClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"

DEFAULT_SYSTEM_PROMPT = """\
You are a helpful assistant that helps meteorologists and forecasters evaluate and compare \
weather forecast models. You have access to the Sheerwater benchmarking platform through various tools.

When a user asks about forecast models:
1. Use the discovery tools to show available models, metrics, and datasets
2. Use the evaluation tools to compare forecasts against ground truth
3. Use the visualization tools to generate charts or dashboard links

Be concise and helpful. When presenting data, format it clearly."""


class ChatService:
    """Service for handling chat interactions with Claude and MCP tools."""

    def __init__(self, anthropic_api_key: str, mcp_client: McpClient):
        self.client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)
        self.mcp_client = mcp_client

    async def send_message(
        self,
        messages: list[dict],
        model: str | None = None,
        system_prompt: str | None = None,
        on_tool_call: Callable[[str, Any], None] | None = None,
    ) -> dict:
        """
        Send a message to Claude with MCP tools available.

        Args:
            messages: Conversation history in Claude format
            model: Claude model to use (defaults to DEFAULT_MODEL)
            system_prompt: System prompt to use (defaults to DEFAULT_SYSTEM_PROMPT)
            on_tool_call: Optional callback when a tool is called (for streaming updates)

        Returns:
            Assistant's response with content and any tool calls made
        """
        model = model or DEFAULT_MODEL
        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        tools = self.mcp_client.get_tools_for_claude()

        # Initial Claude API call
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
        except anthropic.APIConnectionError as e:
            logger.error(f"Anthropic API connection failed: {e.__cause__}")
            raise

        # Handle tool use loop
        tool_calls = []
        images = []  # Collect images from tool results
        while response.stop_reason == "tool_use":
            # Extract tool use blocks
            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

            # Execute each tool call
            tool_results = []
            for tool_use in tool_use_blocks:
                tool_name = tool_use.name
                tool_input = tool_use.input

                if on_tool_call:
                    on_tool_call(tool_name, tool_input)

                tool_calls.append({"name": tool_name, "input": tool_input})

                try:
                    result = await self.mcp_client.call_tool(tool_name, tool_input)
                    # Extract content from MCP result
                    tool_result_content = ""
                    if hasattr(result, "content") and result.content:
                        for content_item in result.content:
                            # Handle image content
                            if hasattr(content_item, "type") and content_item.type == "image":
                                # Store image for frontend display
                                mime_type = getattr(content_item, "mimeType", "image/png")
                                images.append({
                                    "data": content_item.data,
                                    "mimeType": mime_type,
                                })
                                # Tell Claude we generated an image
                                tool_result_content += "[Chart image generated successfully]"
                            elif hasattr(content_item, "text"):
                                tool_result_content += content_item.text
                            else:
                                tool_result_content += str(content_item)
                    else:
                        tool_result_content = str(result)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    tool_result_content = f"Error: {str(e)}"

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_result_content,
                    }
                )

            # Continue conversation with tool results
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results},
            ]

            response = await self.client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

        # Extract final text response
        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content += block.text

        # Prepend images as markdown data URLs so they render in the chat
        if images:
            image_markdown = ""
            for img in images:
                mime_type = img.get("mimeType", "image/png")
                data = img["data"]
                image_markdown += f"![Chart](data:{mime_type};base64,{data})\n\n"
            text_content = image_markdown + text_content

        return {
            "content": text_content,
            "tool_calls": tool_calls,
        }

    def format_messages_for_claude(self, db_messages: list[dict]) -> list[dict]:
        """Convert database messages to Claude API format."""
        claude_messages = []
        for msg in db_messages:
            claude_messages.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                }
            )
        return claude_messages
