import os
from typing import Literal, Sequence

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import Annotated, TypedDict

from app.configs import agent_config, llm_config



class InitState(TypedDict):
    """LangGraph state for the instructor agent."""

    messages: Annotated[list[AnyMessage], add_messages]

    user_name: str
    sudo: bool
    intent: dict | None
    knowledge_context: list[str]
    plan: dict | None
    llm_calls: int