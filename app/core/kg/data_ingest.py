# Configure Graphiti
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from openai import AsyncOpenAI
from graphiti_core.llm_client import OpenAIClient, LLMConfig
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import logging
import sys


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


logger = setup_logging()

config = LLMConfig(
    api_key="sk-orsgnhlexlkmmlszeqwtgjhxbnimvxydtjdeyueqtamindpo",
    base_url="https://api.siliconflow.cn/v1",
    model="deepseek-ai/DeepSeek-V3.2-Exp",
    small_model="deepseek-ai/DeepSeek-V3.2-Exp",
    temperature=0.2,
    max_tokens=1024,
)
embedder_config = OpenAIEmbedderConfig(
    api_key="sk-orsgnhlexlkmmlszeqwtgjhxbnimvxydtjdeyueqtamindpo",
    base_url="https://api.siliconflow.cn/v1",
    embedding_model="BAAI/bge-m3",
    embedding_dim=1024,
)

openai_client = OpenAIClient(
    client=AsyncOpenAI(api_key="sk-orsgnhlexlkmmlszeqwtgjhxbnimvxydtjdeyueqtamindpo", base_url="https://api.siliconflow.cn/v1"), config=config
)
embedder = OpenAIEmbedder(config=embedder_config)
reranker_client = OpenAIRerankerClient(config=config)

neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

client = Graphiti(neo4j_uri, neo4j_user, neo4j_password, llm_client=openai_client, embedder=embedder, cross_encoder=reranker_client)


async def ingest_products_data(client: Graphiti):
    script_dir = Path.cwd().parent
    json_file_path = script_dir / "data" / "manybirds_products.json"

    with open(json_file_path) as file:
        products = json.load(file)["products"]

    for i, product in enumerate(products):
        await client.add_episode(
            name=product.get("title", f"Product {i}"),
            episode_body=str({k: v for k, v in product.items() if k != "images"}),
            source_description="ManyBirds products",
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
        )


# await ingest_products_data(client)
