# -*- coding: utf-8 -*-
# @Time   : 2025/8/13 14:34
# @Author : Galleons
# @File   : embedding.py

"""
embedding function
"""

from typing import Dict
from app.configs import llm_config
import requests

headers = {"Authorization": "Bearer " + llm_config.SILICON_KEY, "Content-Type": "application/json"}


def embedd_text_tolist(text: str) -> list[int]:
    # embedding_list = embed_model.create_embedding(text)['data'][0]['embedding']
    payload = {"model": "BAAI/bge-m3", "input": text}
    embedding_list = requests.post(llm_config.SILICON_EMBEDDING, json=payload, headers=headers).json()["data"][0]["embedding"]
    return embedding_list


def image_embedding(url: str | None = None, path: str | None = None) -> Dict:
    import dashscope

    image = url if url else path
    input = [{"image": image}]

    # 调用模型接口
    from app.configs import llm_config

    dashscope.api_key = llm_config.ALI_KEY

    response = dashscope.MultiModalEmbedding.call(model="multimodal-embedding-v1", input=input)

    # if response.status_code == 200:
    #     result = {
    #         "status_code": resp.status_code,
    #         "request_id": getattr(resp, "request_id", ""),
    #         "code": getattr(resp, "code", ""),
    #         "message": getattr(resp, "message", ""),
    #         "output": resp.output,
    #         "usage": resp.usage
    #     }

    return response.output["embeddings"][0]["embedding"]


if __name__ == "__main__":
    import dashscope
    from http import HTTPStatus

    # 实际使用中请将url地址替换为您的图片url地址
    image = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/256_1.png"
    input = [{"image": image}]
    # 调用模型接口

    from app.configs import llm_config

    dashscope.api_key = llm_config.ALI_KEY
    resp = dashscope.MultiModalEmbedding.call(model="multimodal-embedding-v1", input=input)

    if resp.status_code == HTTPStatus.OK:
        result = {
            "status_code": resp.status_code,
            "request_id": getattr(resp, "request_id", ""),
            "embedding": resp.output["embeddings"][0]["embedding"],
            "message": getattr(resp, "message", ""),
            "output": resp.output,
            "usage": resp.usage,
        }
        # print(json.dumps(result, ensure_ascii=False, indent=4))
        print(resp.output["embeddings"][0]["embedding"])
        print(len(resp.output["embeddings"][0]["embedding"]))
        print(result["code"])
    print(resp.status_code == 200)
