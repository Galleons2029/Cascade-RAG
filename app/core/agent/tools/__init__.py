# -*- coding: utf-8 -*-
# @Time   : 2025/8/13 11:12
# @Author : Galleons
# @File   : __init__.py.py

"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph to extend
the capabilities of language models. Currently including tools for web search
and other external integrations.
"""

from langchain_core.tools.base import BaseTool

from .duckduckgo_search import duckduckgo_search_tool

tools: list[BaseTool] = [duckduckgo_search_tool]
