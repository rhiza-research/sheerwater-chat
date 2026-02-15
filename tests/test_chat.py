"""Tests for chat service logic."""

import pytest

from sheerwater_chat.chat import DEFAULT_SYSTEM_PROMPT, ChatService, extract_chart_url


class TestExtractChartUrl:
    """Tests for chart URL extraction from tool results."""

    def test_extracts_html_url(self):
        text = '{"html_url": "https://storage.example.com/chart.html", "png_url": "https://storage.example.com/chart.png"}'
        assert extract_chart_url(text) == "https://storage.example.com/chart.html"

    def test_prefers_html_over_png(self):
        text = '{"png_url": "https://example.com/chart.png", "html_url": "https://example.com/chart.html"}'
        assert extract_chart_url(text) == "https://example.com/chart.html"

    def test_falls_back_to_chart_url(self):
        text = '{"chart_url": "https://example.com/legacy.png"}'
        assert extract_chart_url(text) == "https://example.com/legacy.png"

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
