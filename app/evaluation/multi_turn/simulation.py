# -*- coding: utf-8 -*-
# @Time    : 2025/07/08 8:30 AM
# @Author  : Galleons
# @File    : simulation.py

"""
多轮对话模拟脚本
"""

from openevals.simulators import run_multiturn_simulation, create_llm_simulated_user
from openevals.llm import create_llm_as_judge
from openevals.types import ChatCompletionMessage
from app.configs import llm_config
from langchain_openai import ChatOpenAI

from openai import OpenAI
from dotenv import load_dotenv
import os

# 加载 .env 文件
load_dotenv()

# 读取变量
api_key = os.getenv("API_KEY")

client = OpenAI(api_key=api_key, base_url="https://api.siliconflow.cn/v1")
langchain_client = ChatOpenAI(
    model="Qwen/Qwen3-8B",
    api_key=api_key,
    base_url=llm_config.SILICON_BASE_URL,
)

history = {}


# Your application logic
def app(inputs: ChatCompletionMessage, *, thread_id: str, **kwargs):
    if thread_id not in history:
        history[thread_id] = []
    history[thread_id].append(inputs)

    # inputs is a message object with role and content
    res = client.chat.completions.create(
        model="Qwen/Qwen3-8B",
        messages=[
            {
                "role": "system",
                "content": "You are a patient and understanding customer service agent",
            },
        ]
        + history[thread_id],
    )

    response_message = res.choices[0].message
    history[thread_id].append(response_message)

    return response_message


user = create_llm_simulated_user(
    system="You are an aggressive and hostile customer who wants a refund for their car.",
    # model="Qwen/Qwen3-8B",
    client=langchain_client,
)

trajectory_evaluator = create_llm_as_judge(
    # model="Qwen/Qwen3-8B",
    judge=langchain_client,
    prompt="Based on the below conversation, was the user satisfied?\n{outputs}",
    feedback_key="satisfaction",
)

# Run the simulation directly with the new function
simulator_result = run_multiturn_simulation(
    app=app,
    user=user,
    trajectory_evaluators=[trajectory_evaluator],
    max_turns=5,
)

print(simulator_result)
