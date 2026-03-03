# -*- coding: utf-8 -*-
# @Time   : 2025/8/12 14:33
# @Author : Galleons
# @File   : chat_v1.py

"""
对话接口
"""

# from app.api.dependency import langfuse
from dotenv import load_dotenv

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from redis import Redis as Dragonfly
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.services.cache import DataService, get_dragonfly
from app.configs import llm_config
from app.core.db.postgre import get_session
from app.models.chat_message import ChatHistoryCreate, ChatMessageCreate, ChatSessionCreate, ChatSessionResponse

load_dotenv()

router = APIRouter()


def get_chat():
    """Provide a chat model with safe defaults for tests and dev."""
    model_name = llm_config.LLM_MODEL or "gpt-4o-mini"
    api_key = llm_config.API_KEY or llm_config.SILICON_KEY or "test-api-key"
    base_url = llm_config.SILICON_BASE_URL if llm_config.SILICON_KEY else None
    return ChatOpenAI(model=model_name, temperature=0.2, api_key=api_key, base_url=base_url)


def __messages_to_histories(
    chat_message_human: ChatMessageCreate,
    chat_message_ai: BaseMessage,
) -> (ChatMessageCreate, ChatMessageCreate):
    chat_history_human = ChatHistoryCreate(
        is_human_message=True,
        content=chat_message_human.content,
    )
    chat_history_ai = ChatHistoryCreate(
        is_human_message=False,
        content=chat_message_ai.content,
        metadata_completion_tokens=chat_message_ai.response_metadata["token_usage"]["completion_tokens"],
        metadata_prompt_tokens=chat_message_ai.response_metadata["token_usage"]["prompt_tokens"],
        metadata_total_tokens=chat_message_ai.response_metadata["token_usage"]["total_tokens"],
        metadata_system_fingerprint=chat_message_ai.response_metadata["system_fingerprint"],
        external_id=chat_message_ai.id,
    )
    return chat_history_human, chat_history_ai


@router.post("/chat")
async def new_chat(
    chat_message_human: ChatMessageCreate,
    db: AsyncSession = Depends(get_session),
    df: Dragonfly = Depends(get_dragonfly),
    chat: ChatOpenAI = Depends(get_chat),
) -> ChatSessionResponse:
    # Invoke the OpenAI API to get the AI response.
    message = HumanMessage(content=chat_message_human.content)
    chat_message_ai = await chat.ainvoke([message])

    # Create a new chat session with the first two chat history entries.
    chat_session = ChatSessionCreate(llm_name="LARGE_LANGUAGE_MODEL_NAME")
    new_chat_histories = __messages_to_histories(chat_message_human, chat_message_ai)
    srv = DataService(db, df)
    chat_session_response = await srv.create_chat_session(chat_session, new_chat_histories)
    return chat_session_response


@router.patch("/chat/{chat_id}")
async def continue_chat(
    chat_id: int,
    chat_message_human: ChatMessageCreate,
    db: AsyncSession = Depends(get_session),
    df: Dragonfly = Depends(get_dragonfly),
    chat: ChatOpenAI = Depends(get_chat),
) -> ChatSessionResponse:
    # Check if the chat session exists and refresh the cache.
    srv = DataService(db, df)
    prev_chat_session_response = await srv.read_chat_histories(chat_id)
    if prev_chat_session_response is None:
        raise HTTPException(status_code=404, detail="chat not found")

    # Construct messages from chat histories and then append the new human message.
    chat_histories = prev_chat_session_response.chat_histories
    messages = []
    for i in range(len(chat_histories)):
        if chat_histories[i].is_human_message:
            messages.append(HumanMessage(content=chat_histories[i].content))
        else:
            messages.append(AIMessage(content=chat_histories[i].content))
    messages.append(HumanMessage(content=chat_message_human.content))

    # Invoke the OpenAI API to get the AI response.
    chat_message_ai = await chat.ainvoke(messages)

    # Add two chat history entries to an existing chat session.
    new_chat_histories = __messages_to_histories(chat_message_human, chat_message_ai)
    chat_session_response = await srv.add_chat_histories(prev_chat_session_response, new_chat_histories)
    return chat_session_response


@router.get("/chat/{chat_id}")
async def read_chat_histories(
    chat_id: int,
    db: AsyncSession = Depends(get_session),
    df: Dragonfly = Depends(get_dragonfly),
) -> ChatSessionResponse:
    srv = DataService(db, df)
    chat_session_response = await srv.read_chat_histories(chat_id)
    if chat_session_response is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_session_response
