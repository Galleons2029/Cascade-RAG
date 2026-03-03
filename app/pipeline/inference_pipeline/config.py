from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = str(Path(__file__).parent.parent.parent)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR, env_file_encoding="utf-8")

    # Embeddings config
    EMBEDDING_MODEL_ID: str = "BAAI/bge-m3"
    EMBEDDING_MODEL_MAX_INPUT_LENGTH: int = 1024
    EMBEDDING_SIZE: int = 1024
    EMBEDDING_MODEL_DEVICE: str = "cuda"

    # OpenAI config
    OPENAI_MODEL_ID: str = "gpt-4o-mini"
    OPENAI_API_KEY: str | None = None

    # QdrantDB config
    QDRANT_DATABASE_HOST: str = "localhost"  # Or 'qdrant' if running inside Docker
    QDRANT_DATABASE_PORT: int = 6333

    USE_QDRANT_CLOUD: bool = False
    QDRANT_CLOUD_URL: str = "str"
    QDRANT_APIKEY: str | None = None

    # RAG config
    TOP_K: int = 10
    KEEP_TOP_K: int = 5
    EXPAND_N_QUERY: int = 5

    # LLM Model config
    HUGGINGFACE_ACCESS_TOKEN: str | None = None
    MODEL_ID: str = "Qwen/Qwen3-8B"  # Change this with your Hugging Face model ID to test out your fine-tuned LLM
    DEPLOYMENT_ENDPOINT_NAME: str = "twin"

    MAX_INPUT_TOKENS: int = 1536  # Max length of input text.
    MAX_TOTAL_TOKENS: int = 2048  # Max length of the generation (including input text).
    MAX_BATCH_TOTAL_TOKENS: int = 2048  # Limits the number of tokens that can be processed in parallel during the generation. # noqa: E501

    SILICON_API_KEY: str | None = "sk-gxijztovbtakciuwjwwqyaoxarjfvhuargxkoawhuzsanssm"
    Silicon_base_url: str | None = "https://api.siliconflow.cn/v1"

    Silicon_model_v1: str | None = "Qwen/Qwen3-8B"
    Silicon_model_mini: str | None = "Qwen/Qwen2.5-7B-Instruct"
    Silicon_model_rerank: str | None = "BAAI/bge-reranker-v2-m3"

    AGENT_KEY: str | None = None


settings = Settings()
