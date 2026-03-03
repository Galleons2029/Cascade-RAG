"""Research Tools.

This module provides search and content processing utilities for the research agent,
using Tavily for URL discovery and fetching full webpage content.
"""

import os

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool
from markdownify import markdownify
from tavily import TavilyClient
from typing_extensions import Annotated, Literal

_tavily_client: TavilyClient | None = None


def get_tavily_client() -> TavilyClient:
    """Create Tavily client lazily to avoid import-time env failures."""
    global _tavily_client
    if _tavily_client is None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY is not set")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


def fetch_webpage_content(url: str, timeout: float = 10.0) -> str:
    """Fetch and convert webpage content to markdown.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Webpage content as markdown
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return markdownify(response.text)
    except Exception as e:
        return f"Error fetching content from {url}: {str(e)}"


@tool(parse_docstring=True)
def tavily_search(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 1,
    topic: Annotated[
        Literal["general", "news", "finance"], InjectedToolArg
    ] = "general",
) -> str:
    """Search the web for information on a given query.

    Uses Tavily to discover relevant URLs, then fetches and returns full webpage content as markdown.

    Args:
        query: Search query to execute
        max_results: Maximum number of results to return (default: 1)
        topic: Topic filter - 'general', 'news', or 'finance' (default: 'general')

    Returns:
        Formatted search results with full webpage content
    """
    try:
        # Use Tavily to discover URLs
        search_results = get_tavily_client().search(
            query,
            max_results=max_results,
            topic=topic,
        )
    except Exception as e:
        return f"Tavily search failed: {str(e)}"

    # Fetch full content for each URL
    result_texts = []
    for result in search_results.get("results", []):
        url = result["url"]
        title = result["title"]

        # Fetch webpage content
        content = fetch_webpage_content(url)

        result_text = f"""## {title}
        **URL:** {url}

        {content}

        ---
        """
        result_texts.append(result_text)

    # Format final response
    response = f"""🔍 Found {len(result_texts)} result(s) for '{query}':

        {chr(10).join(result_texts)}"""

    return response

@tool(parse_docstring=True)
def knowledgebase_search(
    query: str,
    config: RunnableConfig,
) -> str:
    """Search the internal knowledge base (vector store) for information relevant to the query.

    Use this tool to find information from uploaded documents and internal knowledge bases
    before or in addition to searching the web. This is especially useful for domain-specific
    or proprietary information that may not be available on the public internet.

    Args:
        query: The search query to look up in the knowledge base
        config: Runtime config (automatically injected, not visible to LLM)

    Returns:
        Retrieved and re-ranked document chunks relevant to the query
    """
    from app.core.rag.retriever import VectorRetriever

    DEFAULT_COLLECTIONS = ["test_kb_e2e"]

    # Read collections from configurable (passed from frontend)
    collections = (config.get("configurable") or {}).get("collections") or DEFAULT_COLLECTIONS

    try:
        retriever = VectorRetriever(query)
        retrieved_docs = retriever.retrieve_top_k(
            k=4,
            collections=collections,
        )
        context = retriever.rerank(hits=retrieved_docs, keep_top_k=3)

        if not context:
            return f"No relevant documents found in knowledge base for query: '{query}'"

        return context
    except Exception as e:
        return f"Knowledge base search failed: {str(e)}"


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - When assessing research gaps: What specific information am I still missing?
    - Before concluding research: Can I provide a complete answer now?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"
