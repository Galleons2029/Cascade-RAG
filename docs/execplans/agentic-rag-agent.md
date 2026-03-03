# Build agentic RAG LangGraph script

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

The ExecPlan requirements live in `.agent/PLANS.md` at the repository root and this plan must be maintained in accordance with that file.

## Purpose / Big Picture

Deliver a new, standalone LangGraph agent script that implements an agentic RAG workflow in one file. After this change, a user can run the script to see an LLM decide whether to call a retrieval tool, grade retrieved context, optionally rewrite the question, and then generate a concise answer. Success is visible by streaming the graph and observing the node updates and a final answer that references the retrieved blog content.

## Progress

- [x] (2026-01-14 16:34Z) Surveyed existing LangGraph agents and configuration in `app/core/agent/graph` and `langgraph.json` to align the new script with repository patterns.
- [x] (2026-01-14 16:36Z) Implemented a new agentic RAG script that mirrors the tutorial flow with lazy document loading, retrieval, grading, rewriting, and answer generation.
- [x] (2026-01-14 16:36Z) Added a runnable entrypoint example and documented how to exercise the graph locally.

## Surprises & Discoveries

None so far.

## Decision Log

- Decision: Keep the new agentic RAG graph as a standalone module without registering it in `langgraph.json`.
  Rationale: Avoids introducing new runtime dependencies or network calls into the default graph registry while still delivering a complete script that can be run directly.
  Date/Author: 2026-01-14 / Codex

## Outcomes & Retrospective

Implemented the new agentic RAG script with a runnable demo entrypoint. Remaining work is limited to optional registration in `langgraph.json` if the graph should be exposed via the LangGraph server.

## Context and Orientation

The repository already exposes multiple LangGraph agents in `app/core/agent/graph`, such as `rag_agent.py` and `default_agent.py`, and these agents are registered in `langgraph.json`. The existing `rag_agent.py` uses a Qdrant-backed retriever and custom logic. The new script will live alongside those agents as a self-contained example that follows the agentic RAG tutorial flow, but it will not change existing agents. The script will build an in-memory vector store from a small set of blog URLs, provide a `@tool` retriever, and assemble a LangGraph state machine with nodes for tool calling, grading, rewriting, and answer generation.

Tool calling refers to the model emitting a structured request to run a Python function decorated with `@tool`, which is then executed by the LangGraph `ToolNode`. A retriever in this plan is a component that returns the most relevant document chunks for a query, backed by embeddings and an in-memory vector store.

## Plan of Work

Create a new Python module at `app/core/agent/graph/agentic_rag_agent.py`. In that file, define constants for the source URLs, chunk size, and overlap used when building the in-memory index. Add helper functions to resolve API keys and build chat models using `init_chat_model`, consistent with existing agent utilities. Implement a lazy retriever builder that loads the blog posts, splits them into chunks, embeds them, and returns a LangChain retriever; cache this so repeated tool calls do not rebuild the index.

Define the retriever tool with `@tool`, then implement node functions that match the tutorial flow: a tool-calling node that decides whether to retrieve, a grading node that returns either generate or rewrite routing decisions, a rewrite node that rephrases the question, and a generation node that answers with retrieved context. Assemble these nodes into a LangGraph `StateGraph(MessagesState)` with the same conditional edges as the tutorial, compile it, and expose it as `agentic_rag_agent`. Add a small `__main__` example that streams the graph and prints each node update so a user can observe the behavior.

## Concrete Steps

From the repository root, add the new script and populate it with the agentic RAG logic described above. The new file should be created at `app/core/agent/graph/agentic_rag_agent.py` and should not trigger network calls at import time.

Run the module directly to validate the script locally:

    cd /Users/apple/PycharmProjects/Bank-copilot
    python app/core/agent/graph/agentic_rag_agent.py

The expected output is a sequence of "Update from node ..." lines followed by a final assistant message that cites information about reward hacking from the retrieved blog content.

## Validation and Acceptance

Acceptance is satisfied when the script runs end to end using configured API keys, prints updates from each LangGraph node (tool decision, retrieval, grading, rewrite if needed, answer generation), and ends with a concise answer grounded in the retrieved blog content. If API keys are missing, the script should fail fast with a clear error message about configuration.

## Idempotence and Recovery

The script uses a cached in-memory vector store, so rerunning it will reuse the same process cache without altering external state. If a run fails mid-way due to missing API keys or network access, set the required environment variables and retry the same command; no cleanup is needed.

## Artifacts and Notes

The primary artifact is the new script file and its console output. A successful run should include a final assistant message similar to:

    Update from node generate_answer
    ... reward hacking can be categorized into two types ...

## Interfaces and Dependencies

The new module will depend on `langgraph.graph.MessagesState`, `langgraph.graph.StateGraph`, `langgraph.prebuilt.ToolNode`, and `langgraph.prebuilt.tools_condition`. It will use `langchain_community.document_loaders.WebBaseLoader`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `langchain_core.vectorstores.InMemoryVectorStore`, and `langchain_openai.OpenAIEmbeddings` for retrieval. The key public symbol will be:

    agentic_rag_agent: CompiledStateGraph

Node functions and signatures to implement in `app/core/agent/graph/agentic_rag_agent.py`:

    def generate_query_or_respond(state: MessagesState) -> dict
    def grade_documents(state: MessagesState) -> Literal["generate_answer", "rewrite_question"]
    def rewrite_question(state: MessagesState) -> dict
    def generate_answer(state: MessagesState) -> dict

Plan Update Notes: Initial plan created to capture the tutorial-derived agentic RAG implementation steps and repository context.
Plan Update Notes: Marked implementation and demo entrypoint steps as complete, recorded the decision to leave `langgraph.json` untouched to minimize side effects, and updated the retrospective accordingly.
