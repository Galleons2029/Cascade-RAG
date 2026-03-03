# -*- coding: utf-8 -*-
# @Time    : 2025/6/5 14:34
# @Author  : Galleons
# @File    : embeddings.py

"""
流式管道——嵌入算子模块
更新：去处本地依赖，全面接入 silicon embedding model API 以方便个人本地化部署
"""

import logging

# from xinference.client import Client
import numpy as np
import requests
from app.configs import llm_config
from openai import OpenAI

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# os.environ['CUDA_VISIBLE_DEVICES'] = '2'
# from FlagEmbedding import BGEM3FlagModel
# embed_model_bge = BGEM3FlagModel('/data/model_cache/bge-m3', use_fp16=True)
# from app.pipeline.feature_pipeline.config import settings

# TODO:重写代码以及图像嵌入
# def embedd_repositories(text: str):
#     model = INSTRUCTOR("hkunlp/instructor-xl")
#     sentence = text
#     instruction = "Represent the structure of the repository"
#     return model.encode([instruction, sentence])

# client = Client("http://localhost:9997")
# embed_model_raw = client.get_model(settings.EMBEDDING_MODEL_ID)
# embed_model = client.get_model(settings.EMBEDDING_MODEL_ID)


url = "https://api.siliconflow.cn/v1/embeddings"
headers = {"Authorization": f"Bearer {llm_config.SILICON_KEY}", "Content-Type": "application/json"}

client = OpenAI(
    api_key=llm_config.SILICON_KEY,
    base_url=llm_config.SILICON_BASE_URL,
)


def get_embedding(text, model="BAAI/bge-m3"):
    text = text.replace("\n", " ")
    return client.embeddings.create(input=[text], model=model).data[0].embedding


def embedd_text(text: str) -> np.ndarray:
    # embedding_list = embed_model.create_embedding(text)['data'][0]['embedding']
    payload = {"model": "BAAI/bge-m3", "input": text}
    embedding_list = requests.post(url, json=payload, headers=headers).json()["data"][0]["embedding"]
    return np.array(embedding_list)


def embedd_text_tolist(text: str) -> list[int]:
    # embedding_list = embed_model.create_embedding(text)['data'][0]['embedding']
    payload = {"model": "BAAI/bge-m3", "input": text}
    embedding_list = requests.post(url, json=payload, headers=headers).json()["data"][0]["embedding"]
    return embedding_list


def hybrid_embedding(texts: list[str]) -> dict:
    # output = embed_model_bge.encode(texts, return_dense=True, return_sparse=True, return_colbert_vecs=False)
    # idx, vals = zip(*output['lexical_weights'][0].items())
    # return {'dense': output['dense_vecs'][0], 'sparse': models.SparseVector(indices=idx, values=vals)}
    pass


if __name__ == "__main__":
    ans = embedd_text("dawdw")
    print(ans)
