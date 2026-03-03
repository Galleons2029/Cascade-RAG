# -*- coding: utf-8 -*-
# @Time   : 2025/8/12 14:35
# @Author : Galleons
# @File   : chat_message.py

"""
这里是文件说明
"""

from typing import Optional, List
from pydantic import BaseModel


# For creating new sessions, excluding IDs and relations.
class ChatSessionCreate(BaseModel):
    llm_name: str


class ChatMessageCreate(BaseModel):
    content: str


# For creating new history entries, excluding IDs and relations.
class ChatHistoryCreate(ChatMessageCreate):
    is_human_message: bool
    metadata_completion_tokens: Optional[int] = None
    metadata_prompt_tokens: Optional[int] = None
    metadata_total_tokens: Optional[int] = None
    metadata_system_fingerprint: Optional[str] = None
    external_id: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    id: int
    content: str
    is_human_message: bool


class ChatSessionResponse(BaseModel):
    chat_session_id: int
    chat_histories: List[ChatHistoryResponse]
