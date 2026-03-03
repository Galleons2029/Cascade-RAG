from bytewax.outputs import DynamicSink, StatelessSinkPartition
from app.core import get_logger
from app.core.db.qdrant import QdrantDatabaseConnector
from app.pipeline.feature_pipeline.models.base import VectorDBDataModel
from qdrant_client.models import Batch
from qdrant_client.http.api_client import UnexpectedResponse

logger = get_logger(__name__)


class QdrantOutput(DynamicSink):
    """
    Bytewax类，用于连接到Qdrant向量数据库。
    继承DynamicSink是因为能够创建不同的接收源（例如，向量和非向量集合）。
    """

    def __init__(self, connection: QdrantDatabaseConnector, sink_type: str):
        self._connection = connection
        self._sink_type = sink_type

        collections = {
            "vector_posts": True,
            "vector_articles": True,
            "vector_others": True,
        }

        for collection_name, is_vector in collections.items():
            try:
                self._connection.get_collection(collection_name=collection_name)
            except Exception:
                logger.warning(
                    "无法访问集合。正在创建新集合...",
                    collection_name=collection_name,
                )

                if is_vector:
                    self._connection.create_vector_collection(collection_name=collection_name)
                else:
                    self._connection.create_non_vector_collection(collection_name=collection_name)

    # def build(self, step_id: str, worker_index: int, worker_count: int, *args, **kwargs) -> StatelessSinkPartition:
    def build(self, step_id: str, worker_index: int, *args, **kwargs) -> StatelessSinkPartition:
        if self._sink_type == "clean":
            return QdrantCleanedDataSink(connection=self._connection)
        elif self._sink_type == "vector":
            return QdrantVectorDataSink(connection=self._connection)
        else:
            raise ValueError(f"不支持的接收类型：{self._sink_type}")


class QdrantCleanedDataSink(StatelessSinkPartition):
    def __init__(self, connection: QdrantDatabaseConnector):
        self._client = connection

    def write_batch(self, items: list[VectorDBDataModel]) -> None:
        payloads = [item.to_payload() for item in items]
        ids, data = zip(*payloads)
        if data[0]["type"] == "documents":
            # collection_name = data[0]["knowledge_id"]
            logger.info(
                "检测到知识库文档插入",
                data=data,
                num=len(ids),
            )
        else:
            collection_name = get_clean_collection(data_type=data[0]["type"])
            self._client.write_data(
                collection_name=collection_name,
                points=Batch(ids=ids, vectors={}, payloads=data),
            )
            logger.info(
                "成功插入请求的向量点",
                collection_name=collection_name,
                num=len(ids),
            )


class QdrantVectorDataSink(StatelessSinkPartition):
    def __init__(self, connection: QdrantDatabaseConnector):
        self._client = connection

    def write_batch(self, items: list[VectorDBDataModel]) -> None:
        # payloads = [item.to_payload() for item in items]
        # logger.debug(f"接收到批量数据：{payloads}")
        # ids, vectors, meta_data = zip(*payloads)
        # dense_vectors = [vec['dense'] for vec in vectors]
        # sparse_vectors = [vec['sparse'] for vec in vectors]
        # logger.debug(f"接收到向量类型：{vectors}，类型为{type(vectors)}")
        #
        # if meta_data[0]["type"] == "documents":
        #         collection_name = f"{str(meta_data[0]['knowledge_id'])}"
        #         try:
        #             self._client.get_collection(collection_name=collection_name)
        #         except UnexpectedResponse:
        #             logger.info(
        #                 "未检测到知识库。正在创建一个新的知识库...",
        #                 collection_name=collection_name,
        #             )
        #             self._client.create_vector_collection(
        #                 collection_name=collection_name
        #             )
        #         logger.debug(
        #             "数据类型：",
        #             datamodels=meta_data,
        #         )
        # else:
        #     collection_name = get_vector_collection(data_type=meta_data[0]["type"])
        #
        # self._client.write_data(
        #     collection_name=collection_name,
        #     points=Batch(
        #         ids=ids,
        #         vectors={"dense": dense_vectors, "sparse": sparse_vectors},
        #         payloads=meta_data
        #     ),
        # )
        payloads = [item.to_payload() for item in items]
        ids, vectors, meta_data = zip(*payloads)
        if meta_data[0]["type"] == "documents":
            collection_name = str(meta_data[0]['knowledge_id'])
            try:
                self._client.get_collection(collection_name=collection_name)
            except UnexpectedResponse:
                logger.info(
                    "未检测到知识库。正在创建一个新的知识库...",
                    collection_name=collection_name,
                )
                self._client.create_vector_collection(collection_name=collection_name)
            logger.debug(
                "数据类型：",
                datamodels=meta_data,
            )
        else:
            collection_name = get_vector_collection(data_type=meta_data[0]["type"])
        self._client.write_data(
            collection_name=collection_name,
            points=Batch(ids=ids, vectors=vectors, payloads=meta_data),
        )

        logger.info(
            "成功插入请求的向量点",
            collection_name=collection_name,
            num=len(ids),
        )


def get_clean_collection(data_type: str) -> str:
    if data_type == "posts":
        return "cleaned_posts"
    elif data_type == "articles":
        return "cleaned_articles"
    elif data_type == "others":
        return "cleaned_others"
    else:
        raise ValueError(f"不支持的数据类型：{data_type}")


def get_vector_collection(data_type: str) -> str:
    if data_type == "posts":
        return "vector_posts"
    elif data_type == "articles":
        return "vector_articles"
    elif data_type == "others":
        return "vector_others"
    else:
        raise ValueError(f"不支持的数据类型：{data_type}")
