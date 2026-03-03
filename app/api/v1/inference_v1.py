# -*- coding: utf-8 -*-
# @Time   : 2025/8/4 12:57
# @Author : Galleons
# @File   : inference_v1.py

"""
推理 API 接口
"""

from dotenv import load_dotenv
import os
from fastapi import APIRouter
from app.pipeline.inference_pipeline.reasoning import ReasoningPipeline

load_dotenv()
api_key = os.getenv("API_KEY")

router = APIRouter()

llm = ReasoningPipeline(mock=False)


def predict(message: str, history: list[list[str]], author: str) -> str:
    """
    使用  深度思考助手生成回复，模拟与你的深度思考助手的对话。

    参数：
        message (str): 用户的输入消息或问题。
        history (List[List[str]]): 用户和Cascade-RAG之间的历史对话记录。
        about_me (str): 关于用户的个人上下文，用于个性化回复。

    返回：
        str: Cascade-RAG生成的回复。
    """

    query = f"我是{author}。请写关于：{message}"
    response = llm.generate(query=query, enable_rag=True, sample_for_evaluation=False)

    return response["answer"]
