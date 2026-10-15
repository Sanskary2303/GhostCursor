"""
Chat Store Abstractions

Customer-owned database storage for Ghost Cursor chat sessions and messages.
Supports PostgreSQL via SQLAlchemy, with adapters for asyncpg, Prisma, or custom repos.
"""

import abc
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from .types import ChatSession, ChatMessage

# Base classes for async repositories
class ChatStore(abc.ABC):
    """Abstract chat store interface"""

    @abc.abstractmethod
    async def create_session(
        self,
        user_id: str,
        tenant_id: str,
        title: str = "New Conversation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatSession:
        pass

    @abc.abstractmethod
    async def get_session(self, session_id: str, user_id: str) -> Optional[ChatSession]:
        pass

    @abc.abstractmethod
    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ChatSession]:
        pass

    @abc.abstractmethod
    async def get_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ChatMessage]:
        pass

    @abc.abstractmethod
    async def append_messages(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict[str, Any]],
    ) -> None:
        pass

    @abc.abstractmethod
    async def count_turns(self, session_id: str, user_id: str) -> int:
        pass

    @abc.abstractmethod
    async def generate_summary_and_title(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple[str, str]:
        pass

    @abc.abstractmethod
    async def update_session_metadata(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        pass

    @abc.abstractmethod
    async def delete_session(self, session_id: str, user_id: str) -> bool:
        pass


# SQL Alchemy Models
Base = declarative_base()

class SQGCBChatSession(Base):
    """SQLAlchemy model for ghost chat sessions"""
    __tablename__ = "ghost_chat_sessions"

    session_id = sa.Column(sa.VARCHAR(64), primary_key=True)
    tenant_id = sa.Column(sa.VARCHAR(64), nullable=False)
    user_id = sa.Column(sa.VARCHAR(128), nullable=False)
    title = sa.Column(sa.VARCHAR(255), default="New Conversation")
    summary = sa.Column(sa.Text)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = sa.Column(
        sa.TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Indexes
    __table_args__ = (
        sa.Index("idx_ghost_sessions_user", tenant_id, user_id, updated_at.desc()),
    )


class SQGCBChatMessage(Base):
    """SQLAlchemy model for ghost chat messages"""
    __tablename__ = "ghost_chat_messages"

    message_id = sa.Column(sa.VARCHAR(64), primary_key=True)
    session_id = sa.Column(sa.VARCHAR(64), sa.ForeignKey("ghost_chat_sessions.session_id"), nullable=False)
    role = sa.Column(sa.VARCHAR(20), nullable=False)
    content = sa.Column(sa.Text, nullable=False)
    tool_calls = sa.Column(sa.JSONB, server_default="'[]'::jsonb")
    client_actions = sa.Column(sa.JSONB, server_default="'[]'::jsonb")
    token_count = sa.Column(sa.Integer, default=0)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')"),
        sa.Index("idx_ghost_messages_session", session_id, created_at.asc()),
    )


# SQLAlchemy Chat Store Implementation
class SQLAlchemyChatStore(ChatStore):
    """SQLAlchemy implementation of ChatStore"""

    def __init__(
        self,
        engine,
        session_factory: Optional[sa.orm.session.Session] = None,
        auto_create_tables: bool = True,
    ):
        self.engine = engine
        self.session_factory = session_factory or sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        if auto_create_tables:
            self._create_tables()

    def _create_tables(self):
        """Create tables if they don't exist"""
        async def _create():
            async with self.engine.begin() as conn:
                # Enable UUID extension if needed
                await conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
                await conn.run_sync(Base.metadata.create_all)

        import asyncio
        try:
            asyncio.run(_create())
        except RuntimeError:
            # Already in an event loop
            import threading
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _create())
                future.result()

    async def _get_session(self) -> AsyncSession:
        """Get a new database session"""
        return self.session_factory()

    async def create_session(
        self,
        user_id: str,
        tenant_id: str,
        title: str = "New Conversation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatSession:
        async with await self._get_session() as session:
            session_id = str(uuid.uuid4())

            db_session = SQGCBChatSession(
                session_id=session_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title=title,
                summary=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            session.add(db_session)
            await session.commit()

            return ChatSession(
                session_id=db_session.session_id,
                tenant_id=db_session.tenant_id,
                user_id=db_session.user_id,
                title=db_session.title,
                summary=db_session.summary,
                created_at=db_session.created_at,
                updated_at=db_session.updated_at,
            )

    async def get_session(self, session_id: str, user_id: str) -> Optional[ChatSession]:
        async with await self._get_session() as session:
            result = await session.get(SQGCBChatSession, session_id)
            if not result:
                return None

            if result.user_id != user_id:
                return None

            return ChatSession(
                session_id=result.session_id,
                tenant_id=result.tenant_id,
                user_id=result.user_id,
                title=result.title,
                summary=result.summary,
                created_at=result.created_at,
                updated_at=result.updated_at,
            )

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ChatSession]:
        async with await self._get_session() as session:
            query = (
                sa.select(SQGCBChatSession)
                .where(SQGCBChatSession.user_id == user_id)
                .order_by(sa.desc(SQGCBChatSession.updated_at))
                .offset(offset)
                .limit(limit)
            )

            result = await session.execute(query)
            sessions = []

            for db_session in result.scalars():
                sessions.append(
                    ChatSession(
                        session_id=db_session.session_id,
                        tenant_id=db_session.tenant_id,
                        user_id=db_session.user_id,
                        title=db_session.title,
                        summary=db_session.summary,
                        created_at=db_session.created_at,
                        updated_at=db_session.updated_at,
                    )
                )

            return sessions

    async def get_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ChatMessage]:
        async with await self._get_session() as session:
            # Verify session ownership
            session_result = await session.get(SQGCBChatSession, session_id)
            if not session_result or session_result.user_id != user_id:
                return []

            query = (
                sa.select(SQGCBChatMessage)
                .where(SQGCBChatMessage.session_id == session_id)
                .order_by(sa.asc(SQGCBChatMessage.created_at))
                .offset(offset)
                .limit(limit)
            )

            result = await session.execute(query)
            messages = []

            for db_message in result.scalars():
                messages.append(
                    ChatMessage(
                        message_id=db_message.message_id,
                        session_id=db_message.session_id,
                        role=db_message.role,
                        content=db_message.content,
                        tool_calls=db_message.tool_calls or [],
                        client_actions=db_message.client_actions or [],
                        token_count=db_message.token_count,
                        created_at=db_message.created_at,
                    )
                )

            return messages

    async def append_messages(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict[str, Any]],
    ) -> None:
        async with await self._get_session() as session:
            # Verify session ownership
            session_result = await session.get(SQGCBChatSession, session_id)
            if not session_result or session_result.user_id != user_id:
                raise ValueError(f"Unauthorized or session not found: {session_id}")

            for msg_data in messages:
                message_id = str(uuid.uuid4())
                db_message = SQGCBChatMessage(
                    message_id=message_id,
                    session_id=session_id,
                    role=msg_data["role"],
                    content=msg_data["content"],
                    tool_calls=msg_data.get("tool_calls", []),
                    client_actions=msg_data.get("client_actions", []),
                    token_count=msg_data.get("token_count", 0),
                )
                session.add(db_message)

            await session.commit()

    async def count_turns(self, session_id: str, user_id: str) -> int:
        async with await self._get_session() as session:
            # Verify session ownership
            session_result = await session.get(SQGCBChatSession, session_id)
            if not session_result or session_result.user_id != user_id:
                return 0

            query = sa.select(sa.func.count()).select_from(SQGCBChatMessage).where(
                SQGCBChatMessage.session_id == session_id
            )

            result = await session.execute(query)
            return result.scalar() or 0

    async def generate_summary_and_title(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple[str, str]:
        async with await self._get_session() as session:
            # Verify session ownership
            session_result = await session.get(SQGCBChatSession, session_id)
            if not session_result or session_result.user_id != user_id:
                raise ValueError(f"Unauthorized or session not found: {session_id}")

            # Get all messages
            query = (
                sa.select(SQGCBChatMessage)
                .where(SQGCBChatMessage.session_id == session_id)
                .order_by(sa.asc(SQGCBChatMessage.created_at))
            )
            result = await session.execute(query)
            messages = result.scalars().all()

            # Generate simple summary and title from content
            if not messages:
                return "Conversation", "New Conversation"

            # Combine content for analysis
            full_text = " ".join([msg.content for msg in messages if msg.role == "assistant"])

            # Simple heuristics for demo
            word_count = len(full_text.split())
            summary = full_text[:200] + "..." if word_count > 50 else full_text
            title = full_text.split("\\n\\n")[0][:50] if full_text else "New Conversation"

            # Update session
            session_result.summary = summary
            await session.commit()

            return summary, title

    async def update_session_metadata(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        async with await self._get_session() as session:
            result = await session.get(SQGCBChatSession, session_id)
            if not result or result.user_id != user_id:
                raise ValueError(f"Unauthorized or session not found: {session_id}")

            if title is not None:
                result.title = title
            if summary is not None:
                result.summary = summary
            result.updated_at = datetime.now(timezone.utc)

            await session.commit()

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        async with await self._get_session() as session:
            result = await session.get(SQGCBChatSession, session_id)
            if not result or result.user_id != user_id:
                return False

            await session.delete(result)
            await session.commit()
            return True


# Type definitions for better type checking
@dataclass
class ChatSession:
    """Chat session model"""
    session_id: str
    tenant_id: str
    user_id: str
    title: str
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "title": self.title,
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ChatMessage:
    """Chat message model"""
    message_id: str
    session_id: str
    role: str
    content: str
    tool_calls: List[Dict[str, Any]]
    client_actions: List[Dict[str, Any]]
    token_count: int
    created_at: datetime

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "token_count": self.token_count,
            "created_at": self.created_at.isoformat(),
        }