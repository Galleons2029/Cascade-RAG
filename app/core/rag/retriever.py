import concurrent.futures

from qdrant_client import models

# from app.pipeline.feature_pipeline.utils.embeddings import embed_model
from app.pipeline.feature_pipeline.utils.embeddings import embedd_text_tolist
import app.core.logger_utils as logger_utils
from app.core import lib
from app.core.db.qdrant import QdrantDatabaseConnector
from app.core.rag.query_expansion import QueryExpansion
from app.core.rag.reranking import Reranker
from app.core.rag.self_query import SelfQuery

logger = logger_utils.get_logger(__name__)


class VectorRetriever:
    """
    Class for retrieving vectors from a Vector store in a RAG system using query expansion and Multitenancy search.
    """

    def __init__(self, query: str) -> None:
        self._client = QdrantDatabaseConnector()
        self.query = query
        # self._embedder = embed_model
        self._query_expander = QueryExpansion()
        self._metadata_extractor = SelfQuery()
        self._reranker = Reranker()

    def _search_single_query(self, generated_query: str, collections: list[str], metadata_filter_value: dict = None, k: int = 5):
        # assert k > 3, "查询集合限制，k应该小于3"
        # 生成查询向量
        # query_vector = self._embedder.create_embedding(generated_query)['data'][0]['embedding']
        query_vector = embedd_text_tolist(generated_query)

        # 初始化存储各集合查询结果的列表
        vectors = []

        # 通用过滤条件
        if metadata_filter_value:
            filter_condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key=metadata_filter_value["key"],
                        match=models.MatchValue(
                            value=metadata_filter_value["value"],
                        ),
                    )
                ]
            )
        else:
            filter_condition = None

        # 遍历集合并进行搜索
        for collection_name in collections:
            # 执行搜索并添加到 vectors 列表中
            vectors.append(
                self._client.search(
                    collection_name=collection_name,
                    query_filter=filter_condition,
                    query_vector=query_vector,
                    limit=k // len(collections),
                )
            )
            logger.debug(f"收到结果：{vectors[-1]}")
        return lib.flatten(vectors)

    def multi_query(self, to_expand_to_n_queries: int = 3, stream: bool | None = False):
        # TODO: 完善流式管道
        if stream:
            logger.debug(f"进入类型{stream}")
            return self._query_expander.generate_response(self.query, to_expand_to_n=to_expand_to_n_queries)
        else:
            logger.debug("进入生成查询中。。。。")

            generated_queries = self._query_expander.generate_response(self.query, to_expand_to_n=to_expand_to_n_queries, stream=stream)
            logger.debug(f"生成generated_queries：{type(generated_queries)}")
            return generated_queries

    # @opik.track(name="retriever.retrieve_top_k")
    def retrieve_top_k(
        self,
        k: int,
        collections: list[str],
        filter_setting: dict | None = None,
        generated_queries=list[str],
        to_expand_to_n_queries: int = 3,
    ) -> list:
        generated_queries = self._query_expander.generate_response(self.query, to_expand_to_n=to_expand_to_n_queries)
        logger.info(
            "成功进行多查询检索",
            num_queries=len(generated_queries),
        )
        with concurrent.futures.ThreadPoolExecutor() as executor:
            search_tasks = [executor.submit(self._search_single_query, query, collections, filter_setting, k) for query in generated_queries]

            hits = [task.result() for task in concurrent.futures.as_completed(search_tasks)]
            hits = lib.flatten(hits)

        logger.info("All documents retrieved successfully.", num_documents=len(hits))

        return hits

    def _get_relevant_documents(
        self,
        k: int,
        collections: list[str] = ["zsk_test"],
        filter_setting: dict | None = None,
        to_expand_to_n_queries: int = 3,
    ) -> list:
        generated_queries = self._query_expander.generate_response(self.query, to_expand_to_n=to_expand_to_n_queries)
        logger.info(
            "成功进行多查询检索",
            num_queries=len(generated_queries),
        )
        with concurrent.futures.ThreadPoolExecutor() as executor:
            search_tasks = [executor.submit(self._search_single_query, query, collections, filter_setting, k) for query in generated_queries]

            hits = [task.result() for task in concurrent.futures.as_completed(search_tasks)]
            hits = lib.flatten(hits)

        logger.info("All documents retrieved successfully.", num_documents=len(hits))

        return hits

    def rerank(self, hits: list, keep_top_k: int) -> list[str]:
        content_list = [hit.payload["content"] for hit in hits]

        if not content_list:
            content_list = ["知识库为空！！！"]
        rerank_hits = self._reranker.generate_response(query=self.query, passages=content_list, keep_top_k=keep_top_k)

        logger.info("成功重新排序文档。", num_documents=len(rerank_hits))

        return rerank_hits

    def set_query(self, query: str):
        self.query = query
