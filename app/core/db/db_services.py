# -*- coding: utf-8 -*-
# @Time   : 2025/8/20 13:34
# @Author : Galleons
# @File   : db_services.py

"""
Async Database service using SQLModel + SQLAlchemy AsyncSession.

Provides CRUD for Users and Sessions and a health check on the async engine.
"""

from typing import (
    List,
    Optional,
)

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs import (
    Environment,
    agent_config as app_settings,
)
from app.core.logger_utils import logger
from app.core.db.postgre import engine as async_engine, async_session
from app.models.session import Session as ChatSession
from app.models.user import User
# Import permission models to ensure they are registered with SQLModel metadata
from app.models.permission import (  # noqa: F401
    AuditLog,
    KnowledgeBasePermission,
    UserKnowledgeBaseAccess,
)


class DatabaseService:
    """Service class for database operations.

    This class handles all database operations for Users, Sessions, and Messages.
    It uses SQLModel for ORM operations and maintains a connection pool.
    """

    def __init__(self):
        """Prepare async engine and session maker; call init() at startup to create tables."""
        self.engine = async_engine
        self.session_maker: async_sessionmaker[AsyncSession] = async_session

    async def init(self) -> None:
        """Create tables using async engine if not existing."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            logger.info(
                "database_initialized",
                environment=getattr(app_settings.ENVIRONMENT, "value", str(app_settings.ENVIRONMENT)),
            )
        except SQLAlchemyError as e:
            logger.error(
                "database_initialization_error",
                error=str(e),
                environment=getattr(app_settings.ENVIRONMENT, "value", str(app_settings.ENVIRONMENT)),
            )
            if app_settings.ENVIRONMENT != Environment.PRODUCTION:
                raise

    async def create_user(self, email: str, password: str) -> User:
        """Create a new user.

        Args:
            email: User's email address
            password: Hashed password

        Returns:
            User: The created user
        """
        async with self.session_maker() as session:
            user = User(email=email, hashed_password=password)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("user_created", email=email)
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: The ID of the user to retrieve

        Returns:
            Optional[User]: The user if found, None otherwise
        """
        async with self.session_maker() as session:
            return await session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email.

        Args:
            email: The email of the user to retrieve

        Returns:
            Optional[User]: The user if found, None otherwise
        """
        async with self.session_maker() as session:
            statement = select(User).where(User.email == email)
            result = await session.exec(statement)
            return result.first()

    async def delete_user_by_email(self, email: str) -> bool:
        """Delete a user by email.

        Args:
            email: The email of the user to delete

        Returns:
            bool: True if deletion was successful, False if user not found
        """
        async with self.session_maker() as session:
            result = await session.exec(select(User).where(User.email == email))
            user = result.first()
            if not user:
                return False
            await session.delete(user)
            await session.commit()
            logger.info("user_deleted", email=email)
            return True

    async def create_session(self, session_id: str, user_id: int, name: str = "") -> ChatSession:
        """Create a new chat session.

        Args:
            session_id: The ID for the new session
            user_id: The ID of the user who owns the session
            name: Optional name for the session (defaults to empty string)

        Returns:
            ChatSession: The created session
        """
        async with self.session_maker() as session:
            chat_session = ChatSession(id=session_id, user_id=user_id, name=name)
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)
            logger.info("session_created", session_id=session_id, user_id=user_id, name=name)
            return chat_session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID.

        Args:
            session_id: The ID of the session to delete

        Returns:
            bool: True if deletion was successful, False if session not found
        """
        async with self.session_maker() as session:
            chat_session = await session.get(ChatSession, session_id)
            if not chat_session:
                return False
            await session.delete(chat_session)
            await session.commit()
            logger.info("session_deleted", session_id=session_id)
            return True

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID.

        Args:
            session_id: The ID of the session to retrieve

        Returns:
            Optional[ChatSession]: The session if found, None otherwise
        """
        async with self.session_maker() as session:
            return await session.get(ChatSession, session_id)

    async def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        """Get all sessions for a user.

        Args:
            user_id: The ID of the user

        Returns:
            List[ChatSession]: List of user's sessions
        """
        async with self.session_maker() as session:  # type: AsyncSession
            statement = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at)
            result = await session.exec(statement)
            return result.all()

    async def update_session_name(self, session_id: str, name: str) -> ChatSession:
        """Update a session's name.

        Args:
            session_id: The ID of the session to update
            name: The new name for the session

        Returns:
            ChatSession: The updated session

        Raises:
            HTTPException: If session is not found
        """
        async with self.session_maker() as session:  # type: AsyncSession
            chat_session = await session.get(ChatSession, session_id)
            if not chat_session:
                raise HTTPException(status_code=404, detail="Session not found")
            chat_session.name = name
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)
            logger.info("session_name_updated", session_id=session_id, name=name)
            return chat_session

    def get_session_maker(self) -> async_sessionmaker[AsyncSession]:
        """Return the async session maker for advanced use."""

        return self.session_maker

    async def health_check(self) -> bool:
        """Check database connection health.

        Returns:
            bool: True if database is healthy, False otherwise
        """
        try:
            async with self.session_maker() as session:
                await session.exec(select(1))
                return True
        except Exception as e:
            logger.error("database_health_check_failed", error=str(e))
            return False


# Create a singleton instance
database_service = DatabaseService()
