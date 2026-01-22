"""Async database for conversation storage using encode/databases."""

import json
from datetime import UTC, datetime

from databases import Database as DatabaseConnection


class Database:
    """Async database for storing conversations."""

    def __init__(self, database_url: str):
        """
        Initialize database connection.

        Args:
            database_url: Database URL
                - SQLite: sqlite:///./sheerwater_chat.db
                - Postgres: postgresql://user:pass@host/db
        """
        self.database = DatabaseConnection(database_url)

    async def connect(self):
        """Connect to the database."""
        await self.database.connect()
        await self._init_db()

    async def disconnect(self):
        """Disconnect from the database."""
        await self.database.disconnect()

    async def _init_db(self):
        """Initialize database schema."""
        await self.database.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await self.database.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.database.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        await self.database.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)")
        await self.database.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)"
        )

    async def create_conversation(self, conversation_id: str, user_id: str, title: str | None = None) -> dict:
        """Create a new conversation."""
        await self.database.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (:id, :user_id, :title)",
            {"id": conversation_id, "user_id": user_id, "title": title},
        )
        return {"id": conversation_id, "user_id": user_id, "title": title}

    async def get_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        """Get a conversation by ID, ensuring it belongs to the user."""
        row = await self.database.fetch_one(
            "SELECT * FROM conversations WHERE id = :id AND user_id = :user_id",
            {"id": conversation_id, "user_id": user_id},
        )
        return dict(row._mapping) if row else None

    async def list_conversations(self, user_id: str, limit: int = 50) -> list[dict]:
        """List conversations for a user, most recent first."""
        rows = await self.database.fetch_all(
            "SELECT * FROM conversations WHERE user_id = :user_id ORDER BY updated_at DESC LIMIT :limit",
            {"user_id": user_id, "limit": limit},
        )
        return [dict(row._mapping) for row in rows]

    async def update_conversation_title(self, conversation_id: str, user_id: str, title: str):
        """Update conversation title."""
        await self.database.execute(
            "UPDATE conversations SET title = :title, updated_at = :updated_at WHERE id = :id AND user_id = :user_id",
            {"title": title, "updated_at": datetime.now(UTC), "id": conversation_id, "user_id": user_id},
        )

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
    ) -> int:
        """Add a message to a conversation."""
        result = await self.database.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls) VALUES (:conv_id, :role, :content, :tc)",
            {
                "conv_id": conversation_id,
                "role": role,
                "content": content,
                "tc": json.dumps(tool_calls) if tool_calls else None,
            },
        )
        await self.database.execute(
            "UPDATE conversations SET updated_at = :updated_at WHERE id = :id",
            {"updated_at": datetime.now(UTC), "id": conversation_id},
        )
        return result

    async def get_messages(self, conversation_id: str) -> list[dict]:
        """Get all messages in a conversation."""
        rows = await self.database.fetch_all(
            "SELECT * FROM messages WHERE conversation_id = :conv_id ORDER BY created_at ASC",
            {"conv_id": conversation_id},
        )
        messages = []
        for row in rows:
            msg = dict(row._mapping)
            if msg["tool_calls"]:
                msg["tool_calls"] = json.loads(msg["tool_calls"])
            messages.append(msg)
        return messages

    async def delete_conversation(self, conversation_id: str, user_id: str):
        """Delete a conversation and its messages."""
        row = await self.database.fetch_one(
            "SELECT id FROM conversations WHERE id = :id AND user_id = :user_id",
            {"id": conversation_id, "user_id": user_id},
        )
        if row:
            await self.database.execute(
                "DELETE FROM messages WHERE conversation_id = :conv_id",
                {"conv_id": conversation_id},
            )
            await self.database.execute(
                "DELETE FROM conversations WHERE id = :id",
                {"id": conversation_id},
            )

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value by key."""
        row = await self.database.fetch_one(
            "SELECT value FROM settings WHERE key = :key",
            {"key": key},
        )
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str):
        """Set a setting value (insert or update)."""
        await self.database.execute(
            """
            INSERT INTO settings (key, value) VALUES (:key, :value)
            ON CONFLICT(key) DO UPDATE SET value = :value
            """,
            {"key": key, "value": value},
        )

    async def get_all_settings(self) -> dict[str, str]:
        """Get all settings as a dictionary."""
        rows = await self.database.fetch_all("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}
