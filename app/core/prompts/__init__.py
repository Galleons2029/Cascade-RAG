# -*- coding: utf-8 -*-
# @Time   : 2025/8/16 22:38
# @Author : Galleons
# @File   : __init__.py.py

"""This file contains the prompts for the agent."""

import os
from datetime import datetime


def _read_prompt_file(prompt_path: str) -> str:
    with open(os.path.join(os.path.dirname(__file__), prompt_path), "r") as f:
        return f.read()


def load_system_prompt(prompt_path: str, agent_name: str, **kwargs):
    """Load the system prompt from the file."""
    return _read_prompt_file(prompt_path).format(
        agent_name=agent_name,
        current_date_and_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **kwargs,
    )


def load_prompt_template(prompt_path: str) -> str:
    """Load a prompt template without injecting runtime metadata."""
    return _read_prompt_file(prompt_path)


# Main Agent
SYSTEM_PROMPT = load_system_prompt(prompt_path="system.md", agent_name="chief agent")

COORDINATOR_PROMPT = load_system_prompt(prompt_path="coordinator.md", agent_name="Task Coordinator Agent")

INSTRUCTOR_PROMPT = load_system_prompt(prompt_path="instructor.md", agent_name="Task Instructor Agent")

CONTEXTUAL_RETRIEVAL_PROMPT = load_prompt_template(prompt_path="contextual_retrieval.md")
