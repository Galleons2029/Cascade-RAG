# -*- coding: utf-8 -*-
# @Time    : 2025/06/22 11:31 AM
# @Author  : Galleons
# @File    : reasoning_response.py

"""
推理接口响应测试脚本
"""

from openai import OpenAI
from dotenv import load_dotenv
import os

# 加载 .env 文件
load_dotenv()

# 读取变量
api_key = os.getenv("API_KEY")

client = OpenAI(api_key=api_key, base_url="https://api.siliconflow.cn/v1")

response = client.chat.completions.create(
    # model='Pro/deepseek-ai/DeepSeek-R1',
    model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    messages=[{"role": "user", "content": "推理模型会给市场带来哪些新的机会"}],
    stream=True,
    max_tokens=50,
)

for chunk in response:
    if not chunk.choices:
        continue
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta, end="\n", flush=True)
        # print(chunk.id, end="\n", flush=True)

        # print(chunk.choices[0].delta.content, end="", flush=True)
    if chunk.choices[0].delta.reasoning_content:
        # print(chunk.choices[0].delta.reasoning_content, end="", flush=True)
        print(chunk.choices[0].delta, end="\n", flush=True)
