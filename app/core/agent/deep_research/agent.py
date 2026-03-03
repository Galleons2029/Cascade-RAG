"""Research Agent - Standalone script for LangGraph deployment.

This module creates a deep research agent with custom tools and prompts
for conducting web research with strategic thinking and context management.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from deepagents import SubAgent, create_deep_agent
from langchain.chat_models import init_chat_model

# Ensure sibling package `research_agent` is importable when this file is loaded by path.
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from research_agent.prompts import (
    RESEARCH_WORKFLOW_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    SUBAGENT_DELEGATION_INSTRUCTIONS,
)
from research_agent.tools import (
    knowledgebase_search,
    tavily_search,
    think_tool,
)

# Limits
max_concurrent_research_units = 3
max_researcher_iterations = 3

# Get current date
current_date = datetime.now().strftime("%Y-%m-%d")

# Combine orchestrator instructions (RESEARCHER_INSTRUCTIONS only for sub-agents)
INSTRUCTIONS = (
    RESEARCH_WORKFLOW_INSTRUCTIONS
    + "\n\n"
    + "=" * 80
    + "\n\n"
    + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
        max_concurrent_research_units=max_concurrent_research_units,
        max_researcher_iterations=max_researcher_iterations,
    )
)

# Create research sub-agent
research_sub_agent: SubAgent = {
    "name": "research-agent",
    "description": "Delegate research to the sub-agent researcher. Only give this researcher one topic at a time.",
    "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
    "tools": [tavily_search, knowledgebase_search, think_tool],
}

# Model settings aligned with root project configs
model_name = os.getenv("LLM_MODEL") or os.getenv("LLM_MODEL_PRO") or "deepseek-ai/DeepSeek-V3.2"
api_key = os.getenv("LLM_API_KEY") or os.getenv("API_KEY") or os.getenv("SILICON_KEY")
base_url = os.getenv("SILICON_BASE_URL", "https://api.siliconflow.cn/v1")

model_kwargs = {
    "model": model_name,
    "model_provider": "openai",
    "temperature": 0.0,
}
if base_url:
    model_kwargs["base_url"] = base_url
if api_key:
    model_kwargs["api_key"] = api_key

model = init_chat_model(**model_kwargs)

# Create the agent
agent = create_deep_agent(
    model=model,
    tools=[tavily_search, knowledgebase_search, think_tool],
    system_prompt=INSTRUCTIONS,
    subagents=[research_sub_agent],
)
