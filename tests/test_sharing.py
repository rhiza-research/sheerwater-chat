"""Tests for conversation sharing (read-only access)."""

import os
import tempfile

import pytest
import pytest_asyncio

from sheerwater_chat.database import Database


@pytest_asyncio.fixture
async def db():
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(f"sqlite:///{path}")
    await database.connect()
    yield database
    await database.disconnect()
    os.unlink(path)


class TestGetConversationById:
    """Tests for get_conversation_by_id (no user_id filter)."""

    @pytest.mark.asyncio
    async def test_returns_conversation(self, db):
        await db.create_conversation("conv-1", "user-a", "My Chat")
        result = await db.get_conversation_by_id("conv-1")
        assert result is not None
        assert result["id"] == "conv-1"
        assert result["title"] == "My Chat"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, db):
        result = await db.get_conversation_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_other_users_conversation(self, db):
        """Any user's conversation is accessible by ID alone."""
        await db.create_conversation("conv-1", "user-a", "User A's Chat")

        # get_conversation with wrong user returns None
        assert await db.get_conversation("conv-1", "user-b") is None

        # get_conversation_by_id returns it regardless
        result = await db.get_conversation_by_id("conv-1")
        assert result is not None
        assert result["user_id"] == "user-a"


class TestConversationPageReadonly:
    """Tests for read-only conversation page handler logic.

    These test the handler decision logic without running the full app,
    since the pattern is: try owned first, fall back to read-only.
    """

    @pytest.mark.asyncio
    async def test_owner_sees_writable(self, db):
        """Owner gets readonly=False."""
        await db.create_conversation("conv-1", "user-a")

        conversation = await db.get_conversation("conv-1", "user-a")
        readonly = False
        if not conversation:
            conversation = await db.get_conversation_by_id("conv-1")
            readonly = True

        assert conversation is not None
        assert readonly is False

    @pytest.mark.asyncio
    async def test_other_user_sees_readonly(self, db):
        """Non-owner gets readonly=True."""
        await db.create_conversation("conv-1", "user-a")

        conversation = await db.get_conversation("conv-1", "user-b")
        readonly = False
        if not conversation:
            conversation = await db.get_conversation_by_id("conv-1")
            readonly = True

        assert conversation is not None
        assert readonly is True

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self, db):
        """Missing conversation returns None from both methods."""
        conversation = await db.get_conversation("nope", "user-a")
        if not conversation:
            conversation = await db.get_conversation_by_id("nope")

        assert conversation is None
