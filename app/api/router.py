# -*- coding: utf-8 -*-
# @Time    : 2024/10/16 15:58
# @Author  : Galleons
# @File    : routers.py

"""API route composition for v1 endpoints."""

from fastapi import APIRouter

from app.api import services
from app.api.v1 import (
    agent_v1,
    chat_v1,
    doc_parse,
    inference_v1,
    insert_v1,
    kb_manager_v1,
    knowledge_v1,
    search_v1,
    user_management_v1,
)

api_router = APIRouter()

# Core APIs
api_router.include_router(agent_v1.router, prefix="/agent", tags=["agent"])
api_router.include_router(chat_v1.router, prefix="/chat", tags=["chat"])
api_router.include_router(doc_parse.router, prefix="/doc", tags=["doc"])
api_router.include_router(insert_v1.router, prefix="/insert", tags=["insert"])
api_router.include_router(search_v1.router, prefix="/search", tags=["search"])
api_router.include_router(services.auth.router, prefix="/auth", tags=["auth"])

# User Management APIs
api_router.include_router(
    user_management_v1.router, 
    prefix="/user-management", 
    tags=["user-management"]
)

# Existing modules
api_router.include_router(inference_v1.router, prefix="/inference", tags=["inference-v1"])
api_router.include_router(knowledge_v1.router, tags=["knowledge"])
api_router.include_router(kb_manager_v1.router, prefix="/kb-manager", tags=["kb-manager"])
