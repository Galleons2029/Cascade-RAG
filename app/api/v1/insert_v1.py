# -*- coding: utf-8 -*-
# @Time   : 2025/8/13 16:08
# @Author : Galleons
# @File   : insert_v1.py

"""文件上传相关接口。"""

from typing import List

from fastapi import APIRouter
from qdrant_client import models

from app.configs import qdrant_config
from app.core.db.qdrant import QdrantClientManager
from app.core.logger_utils import get_logger
from app.core.rag.embedding import embedd_text_tolist, image_embedding

logger = get_logger(__name__)

router = APIRouter()

COLLECTION_NAME = qdrant_config.COLLECTION_TEST


@router.post(
    "/images_upload/",
    responses={200: {"description": "成功更新岗位信息"}, 400: {"description": "请求数据无效"}, 503: {"description": "Qdrant服务不可用"}},
)
async def image_search(image: str) -> List[int]:
    """批量更新岗位信息

    Args:
        updates: 要更新的岗位信息列表

    Returns:
        tuple[int, List[Dict]]: (成功更新数量, 失败的更新记录列表)
    """
    # updated_count = 0
    # failed_updates = []

    with QdrantClientManager.get_client_context() as qdrant_client:
        if not qdrant_client.collection_exists(COLLECTION_NAME):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "image": models.VectorParams(size=qdrant_config.MULTIMODAL_SIZE, distance=models.Distance.COSINE),
                    "text": models.VectorParams(size=qdrant_config.MULTIMODAL_SIZE, distance=models.Distance.COSINE),
                },
            )

        qdrant_client.upload_points(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    # id=1,
                    vector={
                        "text": embedd_text_tolist("demo"),
                        "image": image_embedding(url=image),
                    },
                )
            ],
        )
