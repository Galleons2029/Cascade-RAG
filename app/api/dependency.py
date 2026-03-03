# -*- coding: utf-8 -*-
# @Time   : 2025/8/4 13:55
# @Author : Galleons
# @File   : dependency.py

"""
依赖配置脚本
"""

from langfuse import Langfuse
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs import agent_config as settings
from app.core.db.postgre import async_session, engine

# Centralized Langfuse client configured from environment via AgentConfig
langfuse = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST,
)


# Expose async engine/session maker for legacy imports; prefer using app.core.db.postgre directly.
postgres_engine: AsyncEngine = engine
AsyncSessionMaker: async_sessionmaker[AsyncSession] = async_session
