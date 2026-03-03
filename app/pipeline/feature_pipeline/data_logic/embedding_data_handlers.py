from abc import ABC, abstractmethod

from app.pipeline.feature_pipeline.models.base import DataModel
from app.pipeline.feature_pipeline.models.chunk import ArticleChunkModel, DocumentChunkModel, PostChunkModel, RepositoryChunkModel
from app.pipeline.feature_pipeline.models.embedded_chunk import (
    ArticleEmbeddedChunkModel,
    PostEmbeddedChunkModel,
    RepositoryEmbeddedChunkModel,
    DocumentEmbeddedChunkModel,
)
from app.pipeline.feature_pipeline.utils.embeddings import embedd_text


class EmbeddingDataHandler(ABC):
    """
    Abstract class for all embedding data handlers.
    All data transformations logic for the embedding step is done here
    """

    @abstractmethod
    def embedd(self, data_model: DataModel) -> DataModel:
        pass


class PostEmbeddingHandler(EmbeddingDataHandler):
    def embedd(self, data_model: PostChunkModel) -> PostEmbeddedChunkModel:
        return PostEmbeddedChunkModel(
            entry_id=data_model.entry_id,
            platform=data_model.platform,
            chunk_id=data_model.chunk_id,
            chunk_content=data_model.chunk_content,
            embedded_content=embedd_text(data_model.chunk_content),
            author_id=data_model.author_id,
            type=data_model.type,
        )


class ArticleEmbeddingHandler(EmbeddingDataHandler):
    def embedd(self, data_model: ArticleChunkModel) -> ArticleEmbeddedChunkModel:
        return ArticleEmbeddedChunkModel(
            entry_id=data_model.entry_id,
            platform=data_model.platform,
            link=data_model.link,
            chunk_content=data_model.chunk_content,
            chunk_id=data_model.chunk_id,
            embedded_content=embedd_text(data_model.chunk_content),
            author_id=data_model.author_id,
            type=data_model.type,
        )


class RepositoryEmbeddingHandler(EmbeddingDataHandler):
    def embedd(self, data_model: RepositoryChunkModel) -> RepositoryEmbeddedChunkModel:
        return RepositoryEmbeddedChunkModel(
            entry_id=data_model.entry_id,
            name=data_model.name,
            link=data_model.link,
            chunk_id=data_model.chunk_id,
            chunk_content=data_model.chunk_content,
            embedded_content=embedd_text(data_model.chunk_content),
            owner_id=data_model.owner_id,
            type=data_model.type,
        )


class DocumentEmbeddingHandler(EmbeddingDataHandler):
    def embedd(self, data_model: DocumentChunkModel) -> DocumentEmbeddedChunkModel:
        return DocumentEmbeddedChunkModel(
            entry_id=data_model.entry_id,
            knowledge_id=data_model.knowledge_id,
            doc_id=data_model.doc_id,
            filename=data_model.filename,
            path=data_model.path,
            chunk_id=data_model.chunk_id,
            chunk_content=data_model.chunk_content,
            embedded_content=embedd_text(data_model.chunk_content),
            # hybrid_vec=hybrid_embedding([data_model.chunk_content]),
            user_id=data_model.user_id,
            images=data_model.images,
            type=data_model.type,
        )
