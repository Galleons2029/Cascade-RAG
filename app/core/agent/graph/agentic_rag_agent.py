# -*- coding: utf-8 -*-
"""Agentic RAG example built with LangGraph.

This module mirrors the LangGraph agentic RAG tutorial in a single script. It
creates a retriever tool over a small set of blog posts, then builds a graph
that decides when to call the tool, grades the retrieved context, optionally
rewrites the question, and generates a concise answer.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field

from app.configs import agent_config, llm_config

DEFAULT_BLOG_URLS: tuple[str, ...] = (
    "https://lilianweng.github.io/posts/2024-11-28-reward-hacking/",
    "https://lilianweng.github.io/posts/2024-07-07-hallucination/",
    "https://lilianweng.github.io/posts/2024-04-12-diffusion-video/",
)

DEFAULT_CHUNK_SIZE = 100
DEFAULT_CHUNK_OVERLAP = 50

GRADE_PROMPT = (
    "You are a grader assessing relevance of a retrieved document to a user question.\n"
    "Here is the retrieved document:\n\n{context}\n\n"
    "Here is the user question: {question}\n"
    "If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.\n"
    "Give a binary score 'yes' or 'no' to indicate whether the document is relevant."
)

REWRITE_PROMPT = (
    "Look at the input and try to reason about the underlying semantic intent / meaning.\n"
    "Here is the initial question:\n"
    "-------\n"
    "{question}\n"
    "-------\n"
    "Formulate an improved question:"
)

GENERATE_PROMPT = (
    "You are an assistant for question-answering tasks. "
    "Use the following pieces of retrieved context to answer the question. "
    "If you don't know the answer, just say that you don't know. "
    "Use three sentences maximum and keep the answer concise.\n"
    "Question: {question}\n"
    "Context: {context}"
)


def _resolve_api_key() -> str | None:
    return (
        agent_config.LLM_API_KEY
        or llm_config.SILICON_KEY
        or llm_config.API_KEY
        or os.getenv("LLM_API_KEY")
        or os.getenv("API_KEY")
    )


def _resolve_base_url() -> str | None:
    return os.getenv("LLM_BASE_URL") or llm_config.SILICON_BASE_URL


def _build_chat_model(model_name: str | None, temperature: float = 0.0):
    resolved_model = (
        model_name
        or llm_config.LLM_MODEL_PRO
        or llm_config.LLM_MODEL
        or agent_config.LLM_MODEL
        or "deepseek-ai/DeepSeek-V3.2"
    )
    return init_chat_model(
        model=resolved_model,
        model_provider="openai",
        api_key=_resolve_api_key(),
        base_url=_resolve_base_url(),
        temperature=temperature,
    )


def _build_embeddings():
    from langchain_openai import OpenAIEmbeddings

    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError("Missing API key. Set LLM_API_KEY, API_KEY, or SILICON_KEY to build embeddings.")

    embedding_model = llm_config.EMBEDDING_MODEL_ID or "text-embedding-3-small"
    return OpenAIEmbeddings(
        model=embedding_model,
        api_key=api_key,
        base_url=_resolve_base_url(),
    )


def _resolve_urls() -> tuple[str, ...]:
    raw = os.getenv("AGENTIC_RAG_URLS")
    if not raw:
        return DEFAULT_BLOG_URLS
    return tuple(url.strip() for url in raw.split(",") if url.strip())


@lru_cache(maxsize=1)
def _build_retriever():
    from langchain_community.document_loaders import WebBaseLoader
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    urls = _resolve_urls()
    docs = []
    for url in urls:
        docs.extend(WebBaseLoader(url).load())

    if not docs:
        raise RuntimeError("No documents loaded for retrieval. Check AGENTIC_RAG_URLS or network access.")

    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )
    doc_splits = text_splitter.split_documents(docs)
    vectorstore = InMemoryVectorStore.from_documents(documents=doc_splits, embedding=_build_embeddings())
    return vectorstore.as_retriever()


@tool
def retrieve_blog_posts(query: str) -> str:
    """Search and return information about the blog posts used in this demo."""
    retriever = _build_retriever()
    docs = retriever.invoke(query)
    if not docs:
        return ""
    return "\n\n".join(doc.page_content for doc in docs)


TOOL_CALLING_MODEL = _build_chat_model(llm_config.TOOL_CALLING_MODEL or llm_config.LLM_MODEL_PRO)
RESPONSE_MODEL = _build_chat_model(llm_config.LLM_MODEL_PRO or llm_config.LLM_MODEL)
GRADER_MODEL = _build_chat_model(llm_config.LLM_MODEL_PRO or llm_config.LLM_MODEL)


class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""

    binary_score: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )


def generate_query_or_respond(state: MessagesState):
    """Decide whether to call the retriever tool or answer directly."""
    response = TOOL_CALLING_MODEL.bind_tools([retrieve_blog_posts]).invoke(state["messages"])
    return {"messages": [response]}


def grade_documents(state: MessagesState) -> Literal["generate_answer", "rewrite_question"]:
    """Determine whether the retrieved documents are relevant to the question."""
    question = state["messages"][0].content
    context = state["messages"][-1].content
    prompt = GRADE_PROMPT.format(question=question, context=context)
    response = GRADER_MODEL.with_structured_output(GradeDocuments).invoke([{"role": "user", "content": prompt}])
    score = str(getattr(response, "binary_score", "")).strip().lower()
    if score == "yes":
        return "generate_answer"
    return "rewrite_question"


def rewrite_question(state: MessagesState):
    """Rewrite the original user question."""
    question = state["messages"][0].content
    prompt = REWRITE_PROMPT.format(question=question)
    response = RESPONSE_MODEL.invoke([{"role": "user", "content": prompt}])
    return {"messages": [HumanMessage(content=response.content)]}


def generate_answer(state: MessagesState):
    """Generate an answer grounded in retrieved context."""
    question = state["messages"][0].content
    context = state["messages"][-1].content
    prompt = GENERATE_PROMPT.format(question=question, context=context)
    response = RESPONSE_MODEL.invoke([{"role": "user", "content": prompt}])
    return {"messages": [response]}


workflow = StateGraph(MessagesState)
workflow.add_node("generate_query_or_respond", generate_query_or_respond)
workflow.add_node("retrieve", ToolNode([retrieve_blog_posts]))
workflow.add_node("rewrite_question", rewrite_question)
workflow.add_node("generate_answer", generate_answer)
workflow.add_edge(START, "generate_query_or_respond")
workflow.add_conditional_edges(
    "generate_query_or_respond",
    tools_condition,
    {
        "tools": "retrieve",
        END: END,
    },
)
workflow.add_conditional_edges("retrieve", grade_documents)
workflow.add_edge("generate_answer", END)
workflow.add_edge("rewrite_question", "generate_query_or_respond")

agentic_rag_agent = workflow.compile()


def _run_demo(question: str) -> None:
    for chunk in agentic_rag_agent.stream({"messages": [{"role": "user", "content": question}]}):
        for node, update in chunk.items():
            print("Update from node", node)
            update["messages"][-1].pretty_print()
            print("\n")


if __name__ == "__main__":
    _run_demo("What does Lilian Weng say about types of reward hacking?")
