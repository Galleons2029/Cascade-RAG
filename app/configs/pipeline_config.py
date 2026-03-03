# -*- coding: utf-8 -*-
# @Time   : 2025/8/1 18:24
# @Author : Galleons
# @File   : pipeline_config.py

"""
pipeline 参数配置
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = str(Path(__file__).parent.parent.parent) + "/.env"


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR, env_file_encoding="utf-8", extra="ignore")

    # Embeddings config
    EMBEDDING_MODEL_ID: str = "bge-m3"
    EMBEDDING_MODEL_MAX_INPUT_LENGTH: int = 512
    EMBEDDING_SIZE: int = 1024
    EMBEDDING_MODEL_DEVICE: str = "gpu"

    # MQ config
    RABBITMQ_DEFAULT_USERNAME: str = "guest"
    RABBITMQ_DEFAULT_PASSWORD: str = "guest"
    RABBITMQ_HOST: str = "mq"  # or localhost if running outside Docker
    RABBITMQ_PORT: int = 5672
    RABBITMQ_QUEUE_NAME: str = "test_files"

    # QdrantDB config
    QDRANT_DATABASE_HOST: str = "qdrant"  # or localhost if running outside Docker
    QDRANT_DATABASE_PORT: int = 6333
    USE_QDRANT_CLOUD: bool = False  # if True, fill in QDRANT_CLOUD_URL and QDRANT_APIKEY
    QDRANT_CLOUD_URL: str | None = None
    QDRANT_APIKEY: str | None = None
