# -*- coding: utf-8 -*-
# @Time   : 2025/8/11 14:04
# @Author : Galleons
# @File   : chatsession.py

"""
User chat session data model
"""

from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    secret_name: str
    dialog_id: int | None = None
    llm_name: str | None = None


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"
    id: Optional[int] = Field(default=None, primary_key=True)
    llm_name: str

    chat_histories: List["ChatHistory"] = Relationship(back_populates="chat_session")


class ChatHistory(SQLModel, table=True):
    __tablename__ = "chat_history"
    id: Optional[int] = Field(default=None, primary_key=True)
    is_human_message: bool
    content: str
    metadata_completion_tokens: Optional[int] = None
    metadata_prompt_tokens: Optional[int] = None
    metadata_total_tokens: Optional[int] = None
    metadata_system_fingerprint: Optional[str] = None
    external_id: Optional[str] = None

    chat_session_id: int | None = Field(foreign_key="chat_session.id")
    chat_session: ChatSession | None = Relationship(back_populates="chat_histories")


# class ChatSession(Base):
#     __tablename__ = "chat_sessions"
#
#     id = Column(Integer, primary_key=True)
#     llm_name = Column(String, nullable=False)
#
#     chat_histories = relationship("ChatHistory", back_populates="chat_session")
#
#
# class ChatHistory(Base):
#     __tablename__ = "chat_histories"
#
#     id = Column(Integer, primary_key=True)
#     chat_session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
#     is_human_message = Column(Boolean, nullable=False)
#     content = Column(String, nullable=False)
#     metadata_completion_tokens = Column(Integer)
#     metadata_prompt_tokens = Column(Integer)
#     metadata_total_tokens = Column(Integer)
#     metadata_system_fingerprint = Column(String)
#     external_id = Column(String)
#
#     chat_session = relationship("ChatSession", back_populates="chat_histories")
