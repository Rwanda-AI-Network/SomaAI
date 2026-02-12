"""Session management using Redis for conversation context.

Uses redis-py directly for session operations as it's simpler
than aiocache for session-style data with complex structures.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime

try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from somaai.cache.config import get_cache_config


@dataclass
class Message:
    """A single message in conversation history."""

    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(**data)


@dataclass
class Session:
    """User session with conversation history."""

    user_id: str
    session_id: str
    messages: list[Message] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "messages": [m.to_dict() for m in self.messages],
                "metadata": self.metadata,
                "created_at": self.created_at,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "Session":
        d = json.loads(data)
        messages = [Message.from_dict(m) for m in d.get("messages", [])]
        return cls(
            user_id=d["user_id"],
            session_id=d["session_id"],
            messages=messages,
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", datetime.utcnow().isoformat()),
        )

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def get_context(self, max_messages: int = 10) -> list[dict]:
        """Get recent messages for LLM context."""
        recent = self.messages[-max_messages:]
        return [{"role": m.role, "content": m.content} for m in recent]


class SessionManager:
    """Manages user sessions with Redis backend.

    Provides conversation context persistence for multi-turn
    interactions.

    Usage:
        manager = SessionManager()
        await manager.connect()

        session = await manager.get_or_create("user123", "session456")
        session.add_message("user", "Hello!")
        await manager.save(session)
    """

    MAX_MESSAGES = 50

    def __init__(
        self,
        redis_url: str | None = None,
        ttl: int | None = None,
        max_messages: int = MAX_MESSAGES,
    ):
        """Initialize session manager.

        Args:
            redis_url: Redis connection URL.
            ttl: Session timeout in seconds.
            max_messages: Maximum messages to retain per session.
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis is required for session management. Install with: uv add redis"
            )

        self.config = get_cache_config()
        self._redis_url = redis_url or self.config.redis_url
        self._ttl = ttl or self.config.session_ttl
        self._max_messages = max_messages
        self._client: redis.Redis | None = None

    def _key(self, user_id: str, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"{self.config.namespace}:session:{user_id}:{session_id}"

    async def connect(self) -> None:
        """Connect to Redis."""
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None

    async def get(self, user_id: str, session_id: str) -> Session | None:
        """Get a session by user and session ID."""
        if not self._client:
            await self.connect()

        key = self._key(user_id, session_id)
        data = await self._client.get(key)

        if data:
            # Refresh TTL on access
            await self._client.expire(key, self._ttl)
            return Session.from_json(data)

        return None

    async def get_or_create(self, user_id: str, session_id: str) -> Session:
        """Get existing session or create new one."""
        session = await self.get(user_id, session_id)

        if session is None:
            session = Session(user_id=user_id, session_id=session_id)
            await self.save(session)

        return session

    async def save(self, session: Session) -> None:
        """Save session to Redis."""
        if not self._client:
            await self.connect()

        # Trim messages if needed
        if len(session.messages) > self._max_messages:
            session.messages = session.messages[-self._max_messages :]

        key = self._key(session.user_id, session.session_id)
        await self._client.setex(key, self._ttl, session.to_json())

    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> Session:
        """Add a message to session and save."""
        session = await self.get_or_create(user_id, session_id)
        session.add_message(role, content)
        await self.save(session)
        return session

    async def delete(self, user_id: str, session_id: str) -> bool:
        """Delete a session."""
        if not self._client:
            await self.connect()

        key = self._key(user_id, session_id)
        deleted = await self._client.delete(key)
        return deleted > 0

    async def update_metadata(
        self,
        user_id: str,
        session_id: str,
        metadata: dict,
    ) -> Session:
        """Update session metadata."""
        session = await self.get_or_create(user_id, session_id)
        session.metadata.update(metadata)
        await self.save(session)
        return session
