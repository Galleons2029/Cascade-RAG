# -*- coding: utf-8 -*-
# @Time    : 2025/06/18 6:28 AM
# @Author  : Galleons
# @File    : test_hybrid_embedding.py

"""
这里是文件说明
"""

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "2"

# from FlagEmbedding import BGEM3FlagModel
# from app.pipeline.feature_pipeline.utils.embeddings import hybrid_embedding, embedd_text
# import numpy as np
#
# #model = BGEM3FlagModel('/data/model_cache/bge-m3', use_fp16=True)
#
# sentences = ["What is BGE M3?", "Defination of BM25"]
#
# def test_hybrid_embedding(text: str):
#
#     assert hybrid_embedding([text]) is dict
#
# def test_dense_embedding(text: str):
#
#     assert embedd_text(text) is np.ndarray
#
