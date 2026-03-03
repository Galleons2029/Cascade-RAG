import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Annotated
from app.configs import llm_config

from dotenv import load_dotenv
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, SystemMessage
from langchain.messages import ToolMessage
from langgraph.graph import END, START, StateGraph, add_messages
from langchain.tools import tool
from langchain.chat_models import init_chat_model

# Configure Graphiti
from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EpisodeType
from openai import AsyncOpenAI
from graphiti_core.llm_client import OpenAIClient, LLMConfig
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_EPISODE_MENTIONS

load_dotenv()


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


logger = setup_logging()

config = LLMConfig(
    api_key=llm_config.SILICON_KEY,
    base_url=llm_config.SILICON_BASE_URL,
    model=llm_config.LLM_MODEL,
    small_model=llm_config.FREE_LLM_MODEL,
    temperature=0.2,
    max_tokens=1024,
)
embedder_config = OpenAIEmbedderConfig(
    api_key=llm_config.SILICON_KEY,
    base_url=llm_config.SILICON_BASE_URL,
    embedding_model="BAAI/bge-m3",
    embedding_dim=1024,
)

openai_client = OpenAIClient(
    client=AsyncOpenAI(api_key=llm_config.SILICON_KEY, base_url=llm_config.SILICON_BASE_URL), config=config
)
embedder = OpenAIEmbedder(config=embedder_config)
reranker_client = OpenAIRerankerClient(config=config)

neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

client = Graphiti(neo4j_uri, neo4j_user, neo4j_password, llm_client=openai_client, embedder=embedder, cross_encoder=reranker_client)


def edges_to_facts_string(entities: list[EntityEdge]):
    return "-" + "\n- ".join([edge.fact for edge in entities])


model = init_chat_model(
    model=llm_config.LLM_MODEL,
    base_url=llm_config.SILICON_BASE_URL,
    api_key=llm_config.SILICON_KEY,
    model_provider="openai",
    temperature=0,
)

user_name = "Galleons"

# Defer node lookups to runtime (avoid awaiting at import time)
_user_node_uuid: str | None = None
_manybirds_node_uuid: str | None = None


async def ensure_node_uuids(user_name_override: str | None = None) -> None:
    """Resolve and cache the user's node UUID and the ManyBirds node UUID.

    This avoids running async code at import-time and prevents coroutine attribute errors.
    """
    global _user_node_uuid, _manybirds_node_uuid
    name = user_name_override or user_name
    try:
        if _user_node_uuid is None:
            nl_user = await client._search(name, NODE_HYBRID_SEARCH_EPISODE_MENTIONS)
            if getattr(nl_user, "nodes", None):
                _user_node_uuid = nl_user.nodes[0].uuid
            else:
                logger.warning(f"No nodes found for user '{name}'")

        if _manybirds_node_uuid is None:
            nl_mb = await client._search("ManyBirds", NODE_HYBRID_SEARCH_EPISODE_MENTIONS)
            if getattr(nl_mb, "nodes", None):
                _manybirds_node_uuid = nl_mb.nodes[0].uuid
            else:
                logger.warning("No nodes found for 'ManyBirds'")
    except Exception as e:
        logger.warning(f"ensure_node_uuids failed: {e}")


# Define tools
@tool
async def get_shoe_data(query: str) -> str:
    """Search the graphiti graph for information about shoes"""
    # Ensure reference node is available
    await ensure_node_uuids()
    if _manybirds_node_uuid is None:
        return "No reference node found for 'ManyBirds'."
    edge_results = await client.search(
        query,
        center_node_uuid=_manybirds_node_uuid,
        num_results=10,
    )
    return edges_to_facts_string(edge_results)


# Augment the LLM with tools
tools = [get_shoe_data]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)


# Step 2: Define state


class State(TypedDict):
    messages: Annotated[list, add_messages]
    user_name: str | None = "Galleons"
    user_node_uuid: str | None


# Step 3: Define model node
async def llm_call(state: State):
    facts_string = None
    if len(state["messages"]) > 0:
        last_message = state["messages"][-1]
        graphiti_query = f"{'SalesBot' if isinstance(last_message, AIMessage) else 'Galleons'}: {last_message.content}"
        # search graphiti using Jess's node uuid as the center node
        # graph edges (facts) further from the Jess node will be ranked lower
        # Ensure we have a center node uuid; fall back to cached user if needed
        # await ensure_node_uuids(state.get('user_name') if isinstance(state, dict) else "Galleons")
        # center_uuid = state.get('user_node_uuid') if isinstance(state, dict) else None
        await ensure_node_uuids("Galleons")
        center_uuid = "c22b0fa3-4ab3-4725-9f95-dbb1b2d2df28"

        if not center_uuid:
            center_uuid = _user_node_uuid
        if center_uuid:
            edge_results = await client.search(graphiti_query, center_node_uuid=center_uuid, num_results=5)
            facts_string = edges_to_facts_string(edge_results)

    system_message = SystemMessage(
        content=f"""You are a skillfull shoe salesperson working for ManyBirds. Review information about the user and their prior conversation below and respond accordingly.
        Keep responses short and concise. And remember, always be selling (and helpful!)

        Things you'll need to know about the user in order to close a sale:
        - the user's shoe size
        - any other shoe needs? maybe for wide feet?
        - the user's preferred colors and styles
        - their budget

        Ensure that you ask the user for the above if you don't already know.

        Facts about the user and their conversation:
        {facts_string or "No facts about the user and their conversation"}"""  # noqa: E501
    )

    messages = [system_message] + state["messages"]

    response = await model.ainvoke(messages)

    # add the response to the graphiti graph.
    # this will allow us to use the graphiti search later in the conversation
    # we're doing async here to avoid blocking the graph execution
    asyncio.create_task(
        client.add_episode(
            name="Chatbot Response",
            episode_body=f"{'Galleons'}: {state['messages'][-1]}\nSalesBot: {response.content}",
            source=EpisodeType.message,
            reference_time=datetime.now(timezone.utc),
            source_description="Chatbot",
        )
    )

    return {"messages": [response]}


# Step 4: Define tool node


async def tool_node(state: dict):
    """Performs the tool call (async-safe)."""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        # Use async invocation to support async tools
        observation = await tool.ainvoke(tool_call["args"])  # type: ignore[attr-defined]
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


# Step 5: Define logic to determine whether to end


# Conditional edge function to route to the tool node or end based upon whether the LLM made a tool call
def should_continue(state: State):
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]

    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"

    # Otherwise, we stop (reply to the user)
    return END


# Step 6: Build agent

# Build workflow
agent_builder = StateGraph(State)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
agent_builder.add_edge("tool_node", "llm_call")

# Compile the agent
agent = agent_builder.compile()