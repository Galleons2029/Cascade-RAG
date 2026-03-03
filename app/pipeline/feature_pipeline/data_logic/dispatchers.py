from app.core import get_logger
from app.pipeline.feature_pipeline.models.base import DataModel
from app.pipeline.feature_pipeline.models.raw import ArticleRawModel, PostsRawModel, RepositoryRawModel, DocumentRawModel

from app.pipeline.feature_pipeline.data_logic.chunking_data_handlers import (
    ArticleChunkingHandler,
    ChunkingDataHandler,
    PostChunkingHandler,
    RepositoryChunkingHandler,
    DocumentChunkingHandler,
)
from app.pipeline.feature_pipeline.data_logic.cleaning_data_handlers import (
    ArticleCleaningHandler,
    CleaningDataHandler,
    PostCleaningHandler,
    RepositoryCleaningHandler,
    DocumentCleaningHandler,
)
from app.pipeline.feature_pipeline.data_logic.embedding_data_handlers import (
    ArticleEmbeddingHandler,
    EmbeddingDataHandler,
    PostEmbeddingHandler,
    RepositoryEmbeddingHandler,
    DocumentEmbeddingHandler,
)

logger = get_logger(__name__)


class RawDispatcher:
    @staticmethod
    def handle_mq_message(message: dict) -> DataModel:
        data_type = message.get("type")

        logger.info("Received message.", data_type=data_type)

        if data_type == "posts":
            return PostsRawModel(**message)
        elif data_type == "articles":
            return ArticleRawModel(**message)
        elif data_type == "repositories":
            return RepositoryRawModel(**message)
        elif data_type == "documents":
            model = DocumentRawModel(**message)
        else:
            logger.error(f"不支持的数据类型: {data_type}")
            raise ValueError("Unsupported data type")

        logger.debug(f"构建的 DataModel: {model}")
        return model


class CleaningHandlerFactory:
    @staticmethod
    def create_handler(data_type) -> CleaningDataHandler:
        if data_type == "posts":
            return PostCleaningHandler()
        elif data_type == "articles":
            return ArticleCleaningHandler()
        elif data_type == "repositories":
            return RepositoryCleaningHandler()
        elif data_type == "documents":
            return DocumentCleaningHandler()
        else:
            logger.error(f"不支持的清理数据类型: {data_type}")
            raise ValueError("Unsupported data type")


class CleaningDispatcher:
    cleaning_factory = CleaningHandlerFactory()

    @classmethod
    def dispatch_cleaner(cls, data_model: DataModel) -> DataModel:
        data_type = data_model.type
        logger.info(f"开始清理数据，类型为 {data_type}: {data_model}")

        try:
            handler = cls.cleaning_factory.create_handler(data_type)
            logger.debug(f"使用的清理处理程序: {handler.__class__.__name__}")
        except Exception as e:
            logger.error(f"创建清理处理程序时发生错误: {e}")
            raise

        try:
            clean_model = handler.clean(data_model)
            logger.debug(f"清理后的 DataModel: {clean_model}")

            assert isinstance(clean_model, DataModel), f"清理后的数据不是 DataModel 类型: {type(clean_model)}"
        except Exception as e:
            logger.error(f"清理数据过程中发生错误: {e}")
            raise

        logger.info(
            "数据成功清洗。",
            data_type=data_type,
            cleaned_content_len=len(clean_model.cleaned_content),
        )

        return clean_model


class ChunkingHandlerFactory:
    @staticmethod
    def create_handler(data_type) -> ChunkingDataHandler:
        if data_type == "posts":
            return PostChunkingHandler()
        elif data_type == "articles":
            return ArticleChunkingHandler()
        elif data_type == "repositories":
            return RepositoryChunkingHandler()
        elif data_type == "documents":
            return DocumentChunkingHandler()
        else:
            logger.error(f"不支持的分块数据类型: {data_type}")
            raise ValueError("Unsupported data type")


class ChunkingDispatcher:
    cleaning_factory = ChunkingHandlerFactory

    @classmethod
    def dispatch_chunker(cls, data_model: DataModel) -> list[DataModel]:
        data_type = data_model.type
        logger.info(f"开始分块数据，类型为 {data_type}: {data_model}")

        try:
            handler = cls.cleaning_factory.create_handler(data_type)
            logger.debug(f"使用的分块处理程序: {handler.__class__.__name__}")
        except Exception as e:
            logger.error(f"创建分块处理程序时发生错误: {e}")
            raise

        try:
            chunk_models = handler.chunk(data_model)
            logger.debug(f"分块后的 DataModel: {chunk_models}")
        except Exception as e:
            logger.error(f"分块数据过程中发生错误: {e}")
            raise

        logger.info(
            "成功将清洗好的内容进行分块。",
            num=len(chunk_models),
            data_type=data_type,
        )

        return chunk_models


class EmbeddingHandlerFactory:
    @staticmethod
    def create_handler(data_type) -> EmbeddingDataHandler:
        if data_type == "posts":
            return PostEmbeddingHandler()
        elif data_type == "articles":
            return ArticleEmbeddingHandler()
        elif data_type == "repositories":
            return RepositoryEmbeddingHandler()
        elif data_type == "documents":
            return DocumentEmbeddingHandler()
        else:
            logger.error(f"不支持的嵌入数据类型: {data_type}")
            raise ValueError("Unsupported data type")


class EmbeddingDispatcher:
    cleaning_factory = EmbeddingHandlerFactory

    @classmethod
    def dispatch_embedder(cls, data_model: DataModel) -> DataModel:
        data_type = data_model.type
        logger.info(f"开始嵌入分块，类型为 {data_type}: {data_model}")

        handler = cls.cleaning_factory.create_handler(data_type)
        embedded_chunk_model = handler.embedd(data_model)

        logger.info(
            "成功嵌入分块。",
            data_type=data_type,
            embedding_len=embedded_chunk_model,
        )

        return embedded_chunk_model
