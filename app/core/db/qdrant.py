# -*- coding: utf-8 -*-
# @Time    : 2025/6/5 14:34
# @Author  : Galleons
# @File    : qdrant.py


from typing import Optional
from contextlib import contextmanager

from qdrant_client import QdrantClient
from qdrant_client.http import models

import app.core.logger_utils as logger_utils
from app.configs import llm_config, qdrant_config


logger = logger_utils.get_logger(__name__)


class QdrantDatabaseConnector:
    _instance: QdrantClient | None = None

    def __init__(self) -> None:
        if self._instance is None:
            if qdrant_config.USE_QDRANT_CLOUD:
                self._instance = QdrantClient(
                    url=qdrant_config.QDRANT_CLOUD_URL,
                    api_key=qdrant_config.QDRANT_APIKEY,
                )
            else:
                self._instance = QdrantClient(
                    host=qdrant_config.QDRANT_DATABASE_HOST,
                    port=qdrant_config.QDRANT_DATABASE_PORT,
                )
                logger.debug("Qdrant连接成功")

    def get_collection(self, collection_name: str):
        return self._instance.get_collection(collection_name=collection_name)

    def create_non_vector_collection(self, collection_name: str):
        self._instance.create_collection(collection_name=collection_name, vectors_config={})

    def create_vector_collection(self, collection_name: str):
        self._instance.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=llm_config.EMBEDDING_SIZE, distance=models.Distance.COSINE),
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                ),
            ),
        )

    def write_data(self, collection_name: str, points: models.Batch):
        try:
            self._instance.upsert(collection_name=collection_name, points=points)
        except Exception:
            logger.exception("An error occurred while inserting data.")

            raise

    def search(
        self,
        collection_name: str,
        query_vector: list,
        query_filter: models.Filter | None = None,
        limit: int = 3,
    ) -> list:
        return self._instance.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        ).points

    def scroll(self, collection_name: str, limit: int):
        return self._instance.scroll(collection_name=collection_name, limit=limit)

    def close(self):
        if self._instance:
            self._instance.close()

            logger.info("Connected to database has been closed.")


class QdrantClientManager:
    _instance: Optional[QdrantClient] = None

    @classmethod
    def get_client(cls) -> QdrantClient:
        """
        获取Qdrant客户端单例实例
        """
        if cls._instance is None:
            try:
                cls._instance = QdrantClient(
                    host=qdrant_config.QDRANT_DATABASE_HOST,
                    port=qdrant_config.QDRANT_DATABASE_PORT,
                )
                logger.info("成功初始化 Qdrant 客户端连接")
            except Exception as e:
                logger.error(f"初始化 Qdrant 客户端失败: {str(e)}")
                raise
        return cls._instance

    @classmethod
    def check_health(cls) -> bool:
        """
        检查Qdrant服务健康状态
        """
        try:
            client = cls.get_client()
            client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant 健康检查失败: {str(e)}")
            return False

    @classmethod
    @contextmanager
    def get_client_context(cls):
        """
        提供上下文管理器方式使用客户端
        """
        client = None
        try:
            client = cls.get_client()
            yield client
        except Exception as e:
            logger.error(f"使用 Qdrant 客户端时发生错误: {str(e)}")
            raise
        finally:
            if client:
                # 这里可以添加任何需要的清理操作
                pass
