# -*- coding: utf-8 -*-
# @Time    : 2025/8/28 15:39
# @Author  : zqh
# @File    : sql_graph.py
import os
import re
from typing import Any, Literal, List

from langchain_community.tools import QuerySQLDatabaseTool
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import StateGraph, MessagesState
from langchain_core.messages import BaseMessage, HumanMessage
from app.configs import postgres_config
from app.core.agent.graph.sql_prompt import  WRITE_QUERY_PROMPT,  CHECK_QUERY_PROMPT, REWRITE_QUERY_PROMPT,detailed_info_prompt
from app.core.config import settings
from dotenv import load_dotenv
from app.core.agent.graph.bank_flow import execute_query_tool
load_dotenv()
pg_host = postgres_config.PG_HOST
pg_port = postgres_config.PG_PORT
pg_user = postgres_config.PG_USER
pg_password = postgres_config.PG_PASSWORD
pg_db = postgres_config.PG_DB
db_uri = f"postgresql+psycopg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
db=SQLDatabase.from_uri(db_uri)
API_KEY = os.getenv("SILICON_KEY") or os.getenv("SILICON_API_KEY")
BASE_URL = os.getenv("SILICON_BASE_URL") or os.getenv("API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL") or "deepseek-ai/DeepSeek-V3"
num_turns = 1
sql_llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=API_KEY,
    base_url=BASE_URL,
    temperature=0.0
)
class State(MessagesState):
    research_topic: str
    raw_notes: str
    compressed_research: str
    researcher_messages: list[BaseMessage]

def parse_query(message: BaseMessage) -> str | None:
    result = None
    for match in re.finditer(r".*```\w*\n(.*?)\n```.*", message.content, re.DOTALL):
        result = match.group(1).strip()
    return result


def get_table_info() -> str:
    """Parse the table information from a string and return it in a dictionary format."""
    original_info=db.get_table_info()
    detail_info=detailed_info_prompt
    return original_info+"\n"+detail_info


def write_query(state: State):
    """
    直接用 LLM 通过 prompt 生成单个 SQL 查询
    """
    prompt = WRITE_QUERY_PROMPT.invoke({
        "dialect": "postgresql",
        "input": state["research_topic"],
        "table_info": get_table_info(),
    })
    llm_res = invoke_prompt(prompt)
    sql_query = parse_query(llm_res) or llm_res.content

    messages = [
        *prompt.messages, llm_res
    ]
    return {
        **state,
        "raw_notes": sql_query,
        "researcher_messages": messages,
    }

def execute_query(state: State) -> State:
    """Execute SQL query."""
    execution_result = execute_query_tool.invoke(state["raw_notes"])
    # if not isinstance(execution_result, str):
    #     # Convert to string if it's not already
    #     execution_result = str(execution_result)

    return {**state, "compressed_research": execution_result}

def truncate_execuion(execution: str) -> str:
    """Truncate the execution result to a reasonable length."""
    if len(execution) > 2048:
        return execution[: 2048] + "\n... (truncated)"
    return execution

def invoke_prompt(prompt: Any) -> BaseMessage:
    try:
        result = sql_llm.invoke(prompt)
    except Exception as e:
        #logger.error(f"Failed to invoke prompt: {e}")
        print(f"Failed to invoke prompt: {e}")
        # FIXME: fallback to create a random trajectory
        result = sql_llm.invoke([HumanMessage(content="Please create a random SQL query as an example.")])

    return result
def check_query(state: State) -> State:
    """Check the SQL query for correctness."""

    prompt = CHECK_QUERY_PROMPT.invoke(
        {
            "dialect": "postgresql",
            "input": state["research_topic"],
            "query": state["raw_notes"],
            "execution": truncate_execuion(state["compressed_research"]),
            "table_info": get_table_info(),
        }
    )

    result = invoke_prompt(prompt)
    res = {
        **state,
        "researcher_messages": [*state.get("researcher_messages", []), *prompt.messages, result],
    }
    return res


def rewrite_query(state: State) -> State:
    """Rewrite SQL query if necessary."""
    global num_turns
    num_turns = num_turns + 1

    # 从 check_query 的结果中提取 feedback
    # feedback 应该是 check_query 返回的最后一个消息内容
    feedback = ""
    researcher_messages = state.get("researcher_messages", [])
    if researcher_messages:
        # 获取最后一个消息作为 feedback
        last_message = researcher_messages[-1]
        if hasattr(last_message, 'content'):
            feedback = last_message.content
        elif isinstance(last_message, dict) and 'content' in last_message:
            feedback = last_message['content']

    prompt = REWRITE_QUERY_PROMPT.invoke(
        {
            "dialect": "postgresql",
            "input": state["research_topic"],
            "query": state["raw_notes"],
            "execution": truncate_execuion(state["compressed_research"]),
            "feedback": feedback,  # 添加 feedback 参数
            "table_info": get_table_info(),
        }
    )
    result = invoke_prompt(prompt)

    rewritten_query = parse_query(result)

    return {
        **state,
        "raw_notes": rewritten_query or state["raw_notes"],
        "compressed_research": [*prompt.messages, result],
    }

def should_continue(state: State) -> Literal[END, "rewrite_query"]:  # type: ignore
    """Determine if the agent should continue based on the result."""
    global num_turns
    if num_turns > 5:
        return END
    if state["researcher_messages"] and isinstance(state["researcher_messages"][-1], BaseMessage):
        last_message = state["researcher_messages"][-1]
        if "THE QUERY IS CORRECT" in last_message.content:
            if "THE QUERY IS INCORRECT" in last_message.content:
                # Both correct and incorrect messages found
                # See which is the last one
                correct_index = last_message.content.rfind("THE QUERY IS CORRECT")
                incorrect_index = last_message.content.rfind("THE QUERY IS INCORRECT")
                if correct_index > incorrect_index:
                    return END
            else:
                if state["compressed_research"] == "":
                    return "rewrite_query"
                return END
    return "rewrite_query"

builder = StateGraph(State)
builder.add_node(write_query)
builder.add_node(execute_query)
builder.add_node(check_query)
builder.add_node(rewrite_query)

builder.add_edge(START, "write_query")
builder.add_edge("write_query", "execute_query")
builder.add_edge("execute_query", "check_query")
builder.add_conditional_edges(
    "check_query",
    should_continue,
)
builder.add_edge("rewrite_query", "execute_query")
sql_graph_test=builder.compile()


def _stringify_execution(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def run_sql_graph(question: str) -> dict[str, Any]:
    global num_turns
    num_turns = 1
    result = sql_graph_test.invoke({"research_topic": question})
    sql_query = result.get("raw_notes", "")
    execution = _stringify_execution(result.get("compressed_research", ""))
    if isinstance(result.get("compressed_research", ""), list) and not result.get("compressed_research"):
        execution = "No rows found; the underlying tables may be missing data for the requested org/sbj/ccy/dt or there were no transactions that day."
    if execution == "[]":
        execution = "No rows found; the underlying tables may be missing data for the requested org/sbj/ccy/dt or there were no transactions that day."
    messages = result.get("researcher_messages", []) or []
    message_lines = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if content:
            message_lines.append(str(content))
    return {
        "sql_query": sql_query,
        "sql_result": execution,
        "sql_messages": message_lines,
    }


if __name__ == "__main__":
    question = "科目号01018114、机构号001570661、币种DUS在2025-06-08的分户余额差是多少？"
    print("问题: " + question)
    try:
        result = sql_graph_test.invoke({"research_topic": question})
        print("\n" + "=" * 50)
        print(f"问题: {result['research_topic']}")
        print("-" * 50)
        print(f"生成的SQL查询:\n{result['raw_notes']}")
        print("-" * 50)
        print(f"执行结果:\n{result['compressed_research']}")
        print("=" * 50)
    except Exception as e:
        print(f"执行出错: {str(e)}")
