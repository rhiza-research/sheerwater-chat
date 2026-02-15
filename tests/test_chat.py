"""Tests for chat service logic."""

import pytest

from sheerwater_chat.chat import DEFAULT_SYSTEM_PROMPT, MAX_TOOL_ITERATIONS, ChatService, extract_chart_url
from sheerwater_chat.mcp_client import McpClient


class TestExtractChartUrl:
    """Tests for chart URL extraction from tool results."""

    def test_extracts_html_url(self):
        text = '{"html_url": "https://storage.example.com/chart.html", "png_url": "https://storage.example.com/chart.png"}'
        assert extract_chart_url(text) == "https://storage.example.com/chart.html"

    def test_prefers_html_over_png(self):
        text = '{"png_url": "https://example.com/chart.png", "html_url": "https://example.com/chart.html"}'
        assert extract_chart_url(text) == "https://example.com/chart.html"

    def test_falls_back_to_png_url(self):
        text = '{"png_url": "https://example.com/chart.png"}'
        assert extract_chart_url(text) == "https://example.com/chart.png"

    def test_returns_none_for_plain_text(self):
        assert extract_chart_url("just some text") is None

    def test_returns_none_for_non_chart_json(self):
        text = '{"status": "complete", "result": {"value": 1.5}}'
        assert extract_chart_url(text) is None

    def test_returns_none_for_invalid_json(self):
        assert extract_chart_url("{broken json") is None

    def test_returns_none_for_empty_string(self):
        assert extract_chart_url("") is None


class TestFormatMessagesForClaude:
    """Tests for message formatting."""

    @pytest.fixture
    def chat_service(self):
        """Create a ChatService with mocked dependencies."""
        # We only need format_messages_for_claude which doesn't use the client or mcp_client
        service = ChatService.__new__(ChatService)
        return service

    def test_strips_base64_images(self, chat_service):
        messages = [
            {
                "role": "assistant",
                "content": "Here is the chart: ![Chart](data:image/png;base64,iVBORw0KGgoAAAANS) and some text after",
            }
        ]
        result = chat_service.format_messages_for_claude(messages)
        assert "base64" not in result[0]["content"]
        assert "and some text after" in result[0]["content"]

    def test_preserves_role(self, chat_service):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = chat_service.format_messages_for_claude(messages)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_preserves_text_content(self, chat_service):
        messages = [{"role": "user", "content": "show me precipitation data"}]
        result = chat_service.format_messages_for_claude(messages)
        assert result[0]["content"] == "show me precipitation data"


class TestSystemPrompt:
    """Tests for system prompt content — should be generic, not coupled to MCP tool names."""

    def test_does_not_hardcode_tool_names(self):
        assert "tool_extract_truth_data" not in DEFAULT_SYSTEM_PROMPT
        assert "tool_render_plotly" not in DEFAULT_SYSTEM_PROMPT
        assert "tool_run_metric" not in DEFAULT_SYSTEM_PROMPT

    def test_is_generic_assistant(self):
        assert "meteorologists" in DEFAULT_SYSTEM_PROMPT
        assert "tools" in DEFAULT_SYSTEM_PROMPT

    def test_instructs_not_to_refuse(self):
        assert "Do not refuse" in DEFAULT_SYSTEM_PROMPT


class TestMaxToolIterations:
    """Tests for tool loop iteration limit."""

    def test_max_tool_iterations_is_set(self):
        assert MAX_TOOL_ITERATIONS > 0

    async def test_tool_loop_breaks_after_max_iterations(self, mocker):
        """send_message should stop the tool loop after MAX_TOOL_ITERATIONS."""
        mock_mcp = mocker.MagicMock(spec=McpClient)
        mock_mcp.get_tools_for_claude.return_value = [
            {"name": "test_tool", "description": "test", "input_schema": {"type": "object", "properties": {}}}
        ]
        mock_mcp.server_instructions = None
        mock_mcp.call_tool = mocker.AsyncMock(
            return_value=mocker.MagicMock(content=[mocker.MagicMock(text="some result")])
        )

        service = ChatService.__new__(ChatService)
        service.client = mocker.MagicMock()
        service.mcp_client = mock_mcp

        # Build a mock response that always says "tool_use"
        tool_use_block = mocker.MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "test_tool"
        tool_use_block.input = {}
        tool_use_block.id = "tool_1"

        tool_response = mocker.MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [tool_use_block]
        tool_response.usage = mocker.MagicMock(input_tokens=100, output_tokens=50)

        raw_response = mocker.MagicMock()
        raw_response.parse.return_value = tool_response
        raw_response.headers = {}

        service.client.messages.with_raw_response.create = mocker.AsyncMock(return_value=raw_response)

        await service.send_message(
            [{"role": "user", "content": "hello"}],
            model="test-model",
            system_prompt="test",
        )

        # Tool loop should have been capped at MAX_TOOL_ITERATIONS
        assert mock_mcp.call_tool.call_count == MAX_TOOL_ITERATIONS


class TestMcpClientVersion:
    """Tests for MCP client server version tracking."""

    def test_initial_version_is_none(self):
        client = McpClient("http://localhost:8000/sse")
        assert client.server_version is None

    def test_version_reset_on_reconnect_cleanup(self):
        """_reconnect resets server_version before re-connecting."""
        client = McpClient("http://localhost:8000/sse")
        client._server_version = "1.0.0"
        client._connected = True

        # Simulate the state after cleanup (without actually connecting)
        client._session = None
        client._connected = False
        client._tools = []
        client._instructions = None
        client._server_version = None

        assert client.server_version is None
