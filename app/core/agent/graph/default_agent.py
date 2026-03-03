# -*- coding: utf-8 -*-
"""
Default agent workflow.

This module intentionally keeps a tiny, tool-calling LangGraph example. It is
exposed via `langgraph.json` as `default_agent` and can be used as a quick
smoke-test for server/UI wiring.

Configuration is read from environment variables (typically via `.env`):
- `LLM_MODEL`: OpenAI-compatible model name.
- `LLM_API_KEY` / `API_KEY`: provider API key.
- `LLM_BASE_URL`: optional OpenAI-compatible base URL.
"""

from __future__ import annotations

import os
from typing import Annotated, Literal

from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.messages import AnyMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict

from app.configs import agent_config, llm_config



DEFAULT_KG: list[str] = ["demo"]

SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful assistant tasked with performing arithmetic on a set of inputs. "
    "You have access to the following knowledge base: {kg}."
)


def _build_llm():
    model_name = agent_config.LLM_MODEL or llm_config.LLM_MODEL or "deepseek-ai/DeepSeek-V3.2"
    api_key = (
        agent_config.LLM_API_KEY
        or llm_config.SILICON_KEY
        or llm_config.API_KEY
        or os.getenv("LLM_API_KEY")
        or os.getenv("API_KEY")
    )
    base_url = os.getenv("LLM_BASE_URL") or llm_config.SILICON_BASE_URL

    return init_chat_model(
        model=model_name,
        model_provider="openai",
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


llm = _build_llm()


@tool
def multiply(a: int, b: int) -> int:
    """Multiply `a` and `b`."""

    return a * b


@tool
def add(a: int, b: int) -> int:
    """Add `a` and `b`."""

    return a + b


@tool
def divide(a: int, b: int) -> float:
    """Divide `a` and `b`."""

    return a / b


TOOLS = [add, multiply, divide]
TOOLS_BY_NAME = {tool_.name: tool_ for tool_ in TOOLS}
LLM_WITH_TOOLS = llm.bind_tools(TOOLS)


class DefaultAgentState(TypedDict):
    """LangGraph state for the default agent."""

    messages: Annotated[list[AnyMessage], add_messages]
    llm_calls: NotRequired[int]
    kg: NotRequired[list[str]]


def llm_call(state: DefaultAgentState):
    """Call the LLM and let it decide whether to invoke a tool."""

    kg = state.get("kg") or DEFAULT_KG
    kg_text = ", ".join(kg)
    system_message = SystemMessage(content=SYSTEM_PROMPT_TEMPLATE.format(kg=kg_text))

    response = LLM_WITH_TOOLS.invoke([system_message, *state["messages"]])
    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def tool_node(state: DefaultAgentState):
    """Execute the tool calls produced by the previous AI message."""

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", []) or []

    tool_messages: list[ToolMessage] = []
    for tool_call in tool_calls:
        tool_ = TOOLS_BY_NAME[tool_call["name"]]
        observation = tool_.invoke(tool_call["args"])
        tool_messages.append(
            ToolMessage(content=str(observation), tool_call_id=tool_call["id"])
        )
    return {"messages": tool_messages}


def should_continue(state: DefaultAgentState) -> Literal["tool_node", "__end__"]:
    """Route to `tool_node` when tool calls exist; otherwise stop."""

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    if tool_calls:
        return "tool_node"
    return END


agent_builder = StateGraph(DefaultAgentState)
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
agent_builder.add_edge("tool_node", "llm_call")

default_agent = agent_builder.compile()
