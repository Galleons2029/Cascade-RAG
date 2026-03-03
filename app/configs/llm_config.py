# -*- coding: utf-8 -*-
# @Time   : 2025/8/13 15:44
# @Author : Galleons
# @File   : llm_config.py

"""
这里是文件说明
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2] / ".env"


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR, env_file_encoding="utf-8", extra="ignore")

    # LLM config
    LLM_MODEL: str | None = None
    LLM_MODEL_PRO: str | None = "deepseek-ai/DeepSeek-V3.2"
    FREE_LLM_MODEL: str | None = "Qwen/Qwen3-8B"
    # 支持 function calling 的模型 (用于 Agent tool binding)
    TOOL_CALLING_MODEL: str | None = "Qwen/Qwen2.5-72B-Instruct"
    DEFAULT_LLM_TEMPERATURE: float = 0.0
    MAX_TOKENS: int | None = 100000

    # Embeddings config
    EMBEDDING_MODEL_ID: str = "bge-m3"
    EMBEDDING_MODEL_MAX_INPUT_LENGTH: int = 512
    EMBEDDING_SIZE: int = 1024
    EMBEDDING_MODEL_DEVICE: str = "gpu"
    EMBEDDING_MODEL_PATH: str | None = None

    # Rerank config
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # 硅基流动API
    SILICON_KEY: str | None = None
    SILICON_BASE_URL: str | None = "https://api.siliconflow.cn/v1"
    SILICON_EMBEDDING: str | None = "https://api.siliconflow.cn/v1/embeddings"

    API_KEY: str | None = None

    ZHIPAI_KEY: str | None = None
    ZHIPAI_BASE_URL: str | None = "https://open.bigmodel.cn/api/paas/v4/"

    # Vision caption (图片理解) config
    VISION_CAPTION_MODEL: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"
    VISION_CAPTION_MAX_IMAGES: int = 20
    VISION_CAPTION_CONCURRENCY: int = 3
    VISION_CAPTION_TIMEOUT_SEC: int = 60
    VISION_CAPTION_MAX_RETRIES: int = 2
    VISION_CAPTION_PROMPT: str = (
        "请用中文简洁描述这张图片的内容，包括图中的关键信息、数据和文字。"
        "只输出描述文本，不要加任何前缀。"
    )
    PUBLIC_BACKEND_BASE_URL: str = "http://localhost:8000"

settings = LLMConfig()


if __name__ == "__main__":
    config = LLMConfig()
    print(config.API_KEY)
    print(ROOT_DIR)
    print(config.LLM_MODEL)
