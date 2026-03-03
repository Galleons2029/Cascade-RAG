# -*- coding: utf-8 -*-
# @Time    : 2025/06/19 3:33 AM
# @Author  : Galleons
# @File    : test_response.py

"""
接口响应测试脚本
"""

# from app.pipeline.inference_pipeline.reasoning import ReasoningPipeline

# inference_endpoint = ReasoningPipeline(mock=False)


def func(x):
    return x + 1


def test_answer():
    assert func(3) == 4
