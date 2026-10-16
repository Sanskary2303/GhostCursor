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
        session_id: Optional[str] = None,
    ) -> ChatSession:
        pass

    @abc.abstractmethod
    async def get_session(self, session_id: str, user_id: str) -> Optional[ChatSession]:
        pass

    @abc.abstractmethod
    async def find_session_by_run(self, run_id: str, user_id: str) -> Optional[ChatSession]:
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
    run_id = sa.Column(sa.VARCHAR(64), index=True, nullable=True)
    role = sa.Column(sa.VARCHAR(20), nullable=False)
    content = sa.Column(sa.Text, nullable=False)
    tool_calls = sa.Column(sa.JSON, default=list)
    client_actions = sa.Column(sa.JSON, default=list)
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
        tenant_id: Optional[str] = None,
    ):
        self.engine = engine
        self.tenant_id = tenant_id
        self.session_factory = session_factory or sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self) -> None:
        """Create tables if they don't exist"""
        async with self.engine.begin() as conn:
            if "postgresql" in str(self.engine.url):
                await conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
            await conn.run_sync(Base.metadata.create_all)

    async def _get_session(self) -> AsyncSession:
        """Get a new database session"""
        return self.session_factory()

    async def create_session(
        self,
        user_id: str,
        tenant_id: str,
        title: str = "New Conversation",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        async with await self._get_session() as session:
            sess_id = session_id or str(uuid.uuid4())

            db_session = SQGCBChatSession(
                session_id=sess_id,
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

    async def find_session_by_run(self, run_id: str, user_id: str) -> Optional[ChatSession]:
        async with await self._get_session() as session:
            query = (
                sa.select(SQGCBChatSession)
                .join(SQGCBChatMessage, SQGCBChatMessage.session_id == SQGCBChatSession.session_id)
                .where(
                    SQGCBChatMessage.run_id == run_id,
                    SQGCBChatSession.user_id == user_id,
                )
            )
            if self.tenant_id:
                query = query.where(SQGCBChatSession.tenant_id == self.tenant_id)
            result = await session.execute(query)
            db_session = result.scalars().first()
            if not db_session:
                return None
            return ChatSession(
                session_id=db_session.session_id,
                tenant_id=db_session.tenant_id,
                user_id=db_session.user_id,
                title=db_session.title,
                summary=db_session.summary,
                created_at=db_session.created_at,
                updated_at=db_session.updated_at,
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
            )
            if self.tenant_id:
                query = query.where(SQGCBChatSession.tenant_id == self.tenant_id)
            query = (
                query.order_by(sa.desc(SQGCBChatSession.updated_at))
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
                        run_id=db_message.run_id,
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
                    run_id=msg_data.get("run_id"),
                    role=msg_data["role"],
                    content=msg_data["content"],
                    tool_calls=msg_data.get("tool_calls", []),
                    client_actions=msg_data.get("client_actions", []),
                    token_count=msg_data.get("token_count", 0),
                )
                session.add(db_message)

            session_result.updated_at = datetime.now(timezone.utc)
            await session.commit()

    async def count_turns(self, session_id: str, user_id: str) -> int:
        async with await self._get_session() as session:
            # Verify session ownership
            session_result = await session.get(SQGCBChatSession, session_id)
            if not session_result or session_result.user_id != user_id:
                return 0

            query = sa.select(sa.func.count()).select_from(SQGCBChatMessage).where(
                SQGCBChatMessage.session_id == session_id,
                SQGCBChatMessage.role == "user",
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
            title = full_text.split("\n\n")[0][:50] if full_text else "New Conversation"

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


class InMemoryChatStore(ChatStore):
    """In-memory implementation of ChatStore for fast local testing and lightweight setups"""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self._sessions: Dict[str, ChatSession] = {}
        self._messages: Dict[str, List[ChatMessage]] = {}

    async def create_tables(self) -> None:
        """No-op for in-memory store"""
        pass

    async def create_session(
        self,
        user_id: str,
        tenant_id: str,
        title: str = "New Conversation",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        sess_id = session_id or str(uuid.uuid4())
        if sess_id in self._sessions:
            raise ValueError("session_id already exists")
        now = datetime.now(timezone.utc)
        session = ChatSession(
            session_id=sess_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            summary=None,
            created_at=now,
            updated_at=now,
        )
        self._sessions[sess_id] = session
        self._messages[sess_id] = []
        return session

    async def get_session(self, session_id: str, user_id: str) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if session and session.user_id == user_id:
            return session
        return None

    async def find_session_by_run(self, run_id: str, user_id: str) -> Optional[ChatSession]:
        for session_id, msgs in self._messages.items():
            for msg in msgs:
                if getattr(msg, "run_id", None) == run_id:
                    sess = self._sessions.get(session_id)
                    if sess and sess.user_id == user_id:
                        if self.tenant_id is None or sess.tenant_id == self.tenant_id:
                            return sess
        return None

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ChatSession]:
        user_sessions = [
            s for s in self._sessions.values()
            if s.user_id == user_id and (self.tenant_id is None or s.tenant_id == self.tenant_id)
        ]
        user_sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return user_sessions[offset : offset + limit]

    async def get_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ChatMessage]:
        session = await self.get_session(session_id, user_id)
        if not session:
            return []
        msgs = self._messages.get(session_id, [])
        return msgs[offset : offset + limit]

    async def append_messages(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict[str, Any]],
    ) -> None:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise ValueError(f"Session not found or unauthorized: {session_id}")

        for msg in messages:
            chat_msg = ChatMessage(
                message_id=msg.get("message_id") or str(uuid.uuid4()),
                session_id=session_id,
                run_id=msg.get("run_id"),
                role=msg["role"],
                content=msg["content"],
                tool_calls=msg.get("tool_calls", []),
                client_actions=msg.get("client_actions", []),
                token_count=msg.get("token_count", 0),
                created_at=msg.get("created_at") or datetime.now(timezone.utc),
            )
            self._messages[session_id].append(chat_msg)

        session.updated_at = datetime.now(timezone.utc)

    async def count_turns(self, session_id: str, user_id: str) -> int:
        session = await self.get_session(session_id, user_id)
        if not session:
            return 0
        msgs = self._messages.get(session_id, [])
        return len([m for m in msgs if m.role == "user"])

    async def generate_summary_and_title(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple[str, str]:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise ValueError(f"Session not found or unauthorized: {session_id}")
        msgs = self._messages.get(session_id, [])
        if not msgs:
            return "Conversation", "New Conversation"
        full_text = " ".join([m.content for m in msgs if m.role == "assistant"])
        summary = full_text[:200] + "..." if len(full_text.split()) > 50 else full_text
        title = full_text.split("\n\n")[0][:50] if full_text else "New Conversation"
        session.summary = summary
        session.title = title
        return summary, title

    async def update_session_metadata(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise ValueError(f"Session not found or unauthorized: {session_id}")
        if title is not None:
            session.title = title
        if summary is not None:
            session.summary = summary
        session.updated_at = datetime.now(timezone.utc)

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        session = await self.get_session(session_id, user_id)
        if not session:
            return False
        self._sessions.pop(session_id, None)
        self._messages.pop(session_id, None)
        return True