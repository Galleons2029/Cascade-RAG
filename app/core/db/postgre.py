# -*- coding: utf-8 -*-
# @Time   : 2025/8/11 11:40
# @Author : Galleons
# @File   : postgre.py

"""
For PostgreSQL Connect,
使用连接池创建，取消单例类
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs import postgres_config

engine: AsyncEngine = create_async_engine(
    postgres_config.postgres_url_async,
    echo=postgres_config.ECHO_SQL,
    pool_size=postgres_config.POOL_SIZE,
    max_overflow=postgres_config.MAX_OVERFLOW,
    pool_timeout=postgres_config.COMMAND_TIMEOUT,
    pool_recycle=postgres_config.POOL_RECYCLE,
    pool_pre_ping=True,  # 断线自动探活
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提升序列化体验
)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async transactional scope for background tasks."""

    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession without auto-commit."""

    async with async_session() as session:
        yield session
