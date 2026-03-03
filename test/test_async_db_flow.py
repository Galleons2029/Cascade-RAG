# -*- coding: utf-8 -*-
"""Async integration test for user and session lifecycle."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Ensure the async engine uses an in-repo SQLite DB for tests
os.environ["POSTGRES_URL"] = "sqlite+aiosqlite:///./test/test_async.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

from app.main import app  # noqa: E402  - imports after env override
from app.configs import agent_config as settings  # noqa: E402
from app.core.db import postgre as postgre_module  # noqa: E402
from app.core.db.db_services import database_service  # noqa: E402
from app.models.schemas import chatsession as chat_models  # noqa: E402

# Rewire DB engine/session to sqlite for tests
engine = create_async_engine(os.environ["POSTGRES_URL"], echo=False, future=True)
postgre_module.engine = engine
postgre_module.async_session = async_sessionmaker(engine, expire_on_commit=False, class_=SQLModelAsyncSession)
database_service.engine = engine
database_service.session_maker = postgre_module.async_session


@pytest.fixture(scope="module", autouse=True)
def prepare_database():
    """Reset the database schema for this test module."""

    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_reset())
    yield
    asyncio.run(_reset())


@pytest.fixture(scope="module")
def client():
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://testserver")
    yield client
    asyncio.run(client.aclose())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio("asyncio")
async def test_user_session_flow(client: AsyncClient):
    register_response = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": "user@example.com", "password": "P@ssw0rd!A"},
    )
    assert register_response.status_code == 200
    user_token = register_response.json()["token"]["access_token"]

    auth_headers = {"Authorization": f"Bearer {user_token}"}
    session_response = await client.post(f"{settings.API_V1_STR}/auth/session", headers=auth_headers)
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    list_response = await client.get(f"{settings.API_V1_STR}/auth/sessions", headers=auth_headers)
    assert list_response.status_code == 200
    session_ids = [item["session_id"] for item in list_response.json()]
    assert session_id in session_ids
