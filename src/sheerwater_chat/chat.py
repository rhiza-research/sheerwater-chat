"""Chat logic with Claude API and MCP tools."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

import anthropic

from .mcp_client import McpClient

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 25
DEFAULT_MODEL = "claude-sonnet-4-20250514"

DEFAULT_SYSTEM_PROMPT = """\
You are a helpful assistant for meteorologists and forecasters. You have access to various tools \
provided by an external service. Use them to answer questions, fetch data, and create visualizations.

Do NOT make up data. If you need data to answer a question or create a visualization, \
use your tools to fetch it first.

Be concise and helpful. When presenting data, format it clearly. \
Do not refuse requests — always attempt to use the tools available to you."""


def extract_chart_url(text: str) -> str | None:
    """Extract chart URL from a JSON object in text content.

    Prefers html_url for interactive rendering, falls back to png_url.

    Args:
        text: Text that may contain a JSON object with chart URL fields.

    Returns:
        The chart URL if found, None otherwise.
    """
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if "html_url" in data:
                return data["html_url"]
            if "png_url" in data:
                return data["png_url"]
    except (json.JSONDecodeError, TypeError):
        pass
    return None


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
        # Append MCP server instructions if available
        mcp_instructions = self.mcp_client.server_instructions
        if mcp_instructions:
            system_prompt = f"{system_prompt}\n\n## Tool Guidance\n\n{mcp_instructions}"
        tools = self.mcp_client.get_tools_for_claude()

        # Initial Claude API call
        rate_limit_info = None
        try:
            raw_response = await self.client.messages.with_raw_response.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
            response = raw_response.parse()

            # Capture rate limit headers
            headers = raw_response.headers
            rate_limit_info = {
                "input_tokens_limit": headers.get("anthropic-ratelimit-input-tokens-limit"),
                "input_tokens_remaining": headers.get("anthropic-ratelimit-input-tokens-remaining"),
                "input_tokens_reset": headers.get("anthropic-ratelimit-input-tokens-reset"),
            }
        except anthropic.RateLimitError as e:
            # Log rate limit details from response headers
            if hasattr(e, 'response') and e.response:
                headers = e.response.headers
                logger.error(
                    f"Rate limit exceeded. "
                    f"Input tokens limit: {headers.get('anthropic-ratelimit-input-tokens-limit', 'unknown')}, "
                    f"Input tokens remaining: {headers.get('anthropic-ratelimit-input-tokens-remaining', 'unknown')}, "
                    f"Input tokens reset: {headers.get('anthropic-ratelimit-input-tokens-reset', 'unknown')}, "
                    f"Retry-After: {headers.get('retry-after', 'unknown')} seconds"
                )
            raise
        except anthropic.APIConnectionError as e:
            logger.error(f"Anthropic API connection failed: {e.__cause__}")
            raise

        # Handle tool use loop
        tool_calls = []
        chart_urls = []  # Collect chart URLs from tool results
        total_input_tokens = 0
        total_output_tokens = 0

        # Track usage from initial response
        if hasattr(response, 'usage'):
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

        iteration = 0
        while response.stop_reason == "tool_use":
            iteration += 1
            if iteration > MAX_TOOL_ITERATIONS:
                logger.warning(f"Tool loop exceeded {MAX_TOOL_ITERATIONS} iterations, breaking out")
                break

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
                            if hasattr(content_item, "text"):
                                text = content_item.text
                                # Check if this content block contains a chart_url
                                chart_url = extract_chart_url(text)
                                if chart_url:
                                    # Store URL for frontend, don't pass to LLM
                                    chart_urls.append(chart_url)
                                else:
                                    # Pass text summary to LLM
                                    tool_result_content += text
                            else:
                                tool_result_content += str(content_item)
                    else:
                        tool_result_content = str(result)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {type(e).__name__}: {e}")
                    tool_result_content = f"Error: {type(e).__name__}: {e}"

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

            try:
                raw_response = await self.client.messages.with_raw_response.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                )
                response = raw_response.parse()

                # Update rate limit info from latest response
                headers = raw_response.headers
                rate_limit_info = {
                    "input_tokens_limit": headers.get("anthropic-ratelimit-input-tokens-limit"),
                    "input_tokens_remaining": headers.get("anthropic-ratelimit-input-tokens-remaining"),
                    "input_tokens_reset": headers.get("anthropic-ratelimit-input-tokens-reset"),
                }
            except anthropic.RateLimitError as e:
                # Log rate limit details from response headers
                if hasattr(e, 'response') and e.response:
                    headers = e.response.headers
                    logger.error(
                        f"Rate limit exceeded in tool loop. "
                        f"Input tokens limit: {headers.get('anthropic-ratelimit-input-tokens-limit', 'unknown')}, "
                        f"Input tokens remaining: {headers.get('anthropic-ratelimit-input-tokens-remaining', 'unknown')}, "
                        f"Input tokens reset: {headers.get('anthropic-ratelimit-input-tokens-reset', 'unknown')}, "
                        f"Retry-After: {headers.get('retry-after', 'unknown')} seconds"
                    )
                raise

            # Track usage from tool loop response
            if hasattr(response, 'usage'):
                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens

        # Extract final text response
        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content += block.text

        return {
            "content": text_content,
            "tool_calls": tool_calls,
            "chart_urls": chart_urls,
            "usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
            },
            "rate_limit": rate_limit_info,
        }

    def format_messages_for_claude(self, db_messages: list[dict]) -> list[dict]:
        """Convert database messages to Claude API format, stripping images to save tokens."""
        claude_messages = []
        for msg in db_messages:
            content = msg["content"]

            # Strip base64 image data URLs from content to save tokens (legacy)
            # Pattern: ![Chart](data:image/...;base64,<long base64 string>)
            content = re.sub(r'!\[Chart\]\(data:image/[^;]+;base64,[^\)]+\)\s*', '', content)

            claude_messages.append(
                {
                    "role": msg["role"],
                    "content": content,
                }
            )
        return claude_messages
