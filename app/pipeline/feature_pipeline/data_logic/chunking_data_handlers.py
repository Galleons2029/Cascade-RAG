import hashlib
from abc import ABC, abstractmethod

from app.pipeline.feature_pipeline.models.base import DataModel
from app.pipeline.feature_pipeline.models.chunk import ArticleChunkModel, DocumentChunkModel, PostChunkModel, RepositoryChunkModel
from app.pipeline.feature_pipeline.models.clean import ArticleCleanedModel, DocumentCleanedModel, PostCleanedModel, RepositoryCleanedModel
from app.pipeline.feature_pipeline.utils.chunking import chunk_text

from app.core import get_logger

logger = get_logger(__name__)


class ChunkingDataHandler(ABC):
    """
    所有分块数据处理程序的抽象类。
    所有分块步骤的数据转换逻辑都在这里完成。
    """

    @abstractmethod
    def chunk(self, data_model: DataModel) -> list[DataModel]:
        pass


class PostChunkingHandler(ChunkingDataHandler):
    def chunk(self, data_model: PostCleanedModel) -> list[PostChunkModel]:
        data_models_list = []

        text_content = data_model.cleaned_content
        chunks = chunk_text(text_content)

        for chunk in chunks:
            model = PostChunkModel(
                entry_id=data_model.entry_id,
                platform=data_model.platform,
                chunk_id=hashlib.md5(chunk.encode()).hexdigest(),
                chunk_content=chunk,
                author_id=data_model.author_id,
                image=data_model.image if data_model.image else None,
                type=data_model.type,
            )
            data_models_list.append(model)

        return data_models_list


class ArticleChunkingHandler(ChunkingDataHandler):
    def chunk(self, data_model: ArticleCleanedModel) -> list[ArticleChunkModel]:
        data_models_list = []

        text_content = data_model.cleaned_content
        chunks = chunk_text(text_content)

        for chunk in chunks:
            model = ArticleChunkModel(
                entry_id=data_model.entry_id,
                platform=data_model.platform,
                link=data_model.link,
                chunk_id=hashlib.md5(chunk.encode()).hexdigest(),
                chunk_content=chunk,
                author_id=data_model.author_id,
                type=data_model.type,
            )
            data_models_list.append(model)

        return data_models_list


class RepositoryChunkingHandler(ChunkingDataHandler):
    def chunk(self, data_model: RepositoryCleanedModel) -> list[RepositoryChunkModel]:
        data_models_list = []

        text_content = data_model.cleaned_content
        chunks = chunk_text(text_content)

        for chunk in chunks:
            model = RepositoryChunkModel(
                entry_id=data_model.entry_id,
                name=data_model.name,
                link=data_model.link,
                chunk_id=hashlib.md5(chunk.encode()).hexdigest(),
                chunk_content=chunk,
                owner_id=data_model.owner_id,
                type=data_model.type,
            )
            data_models_list.append(model)

        return data_models_list


class DocumentChunkingHandler(ChunkingDataHandler):
    def chunk(self, data_model: DocumentCleanedModel) -> list[DocumentChunkModel]:
        data_models_list = []

        text_content = data_model.cleaned_content
        logger.debug(f"对清洗好的数据进行切分: {text_content}")
        chunks = chunk_text(text_content)
        logger.debug(f"切片为: {chunks}")

        for chunk in chunks:
            model = DocumentChunkModel(
                entry_id=data_model.entry_id,
                knowledge_id=data_model.knowledge_id,
                doc_id=data_model.doc_id,
                filename=data_model.filename,
                path=data_model.path,
                chunk_id=hashlib.md5(chunk.encode()).hexdigest(),
                chunk_content=chunk,
                user_id=data_model.user_id,
                image=data_model.image if data_model.image else None,
                images=data_model.images,
                type=data_model.type,
            )
            data_models_list.append(model)

        return data_models_list
