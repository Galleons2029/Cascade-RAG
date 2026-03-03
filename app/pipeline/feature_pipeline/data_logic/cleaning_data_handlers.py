from abc import ABC, abstractmethod

from app.pipeline.feature_pipeline.models.base import DataModel
from app.pipeline.feature_pipeline.models.clean import ArticleCleanedModel, DocumentCleanedModel, PostCleanedModel, RepositoryCleanedModel
from app.pipeline.feature_pipeline.models.raw import ArticleRawModel, PostsRawModel, RepositoryRawModel, DocumentRawModel
from app.pipeline.feature_pipeline.utils.cleaning import clean_text
from pydantic import ValidationError


class CleaningDataHandler(ABC):
    """
    Abstract class for all cleaning data handlers.
    All data transformations logic for the cleaning step is done here
    """

    @abstractmethod
    def clean(self, data_model: DataModel) -> DataModel:
        pass


class PostCleaningHandler(CleaningDataHandler):
    def clean(self, data_model: PostsRawModel) -> PostCleanedModel:
        joined_text = "".join(data_model.content.values()) if data_model and data_model.content else None

        return PostCleanedModel(
            entry_id=data_model.entry_id,
            platform=data_model.platform,
            cleaned_content=clean_text(joined_text),
            author_id=data_model.author_id,
            image=data_model.image if data_model.image else None,
            type=data_model.type,
        )


class ArticleCleaningHandler(CleaningDataHandler):
    def clean(self, data_model: ArticleRawModel) -> ArticleCleanedModel:
        joined_text = "".join(data_model.content.values()) if data_model and data_model.content else None

        return ArticleCleanedModel(
            entry_id=data_model.entry_id,
            platform=data_model.platform,
            link=data_model.link,
            cleaned_content=clean_text(joined_text),
            author_id=data_model.author_id,
            type=data_model.type,
        )


class RepositoryCleaningHandler(CleaningDataHandler):
    def clean(self, data_model: RepositoryRawModel) -> RepositoryCleanedModel:
        joined_text = "".join(data_model.content.values()) if data_model and data_model.content else None

        return RepositoryCleanedModel(
            entry_id=data_model.entry_id,
            name=data_model.name,
            link=data_model.link,
            cleaned_content=clean_text(joined_text),
            owner_id=data_model.owner_id,
            type=data_model.type,
        )


class DocumentCleaningHandler(CleaningDataHandler):
    def clean(self, data_model: DocumentRawModel) -> DocumentCleanedModel:
        doc_model = None
        try:
            doc_model = DocumentCleanedModel(
                entry_id=data_model.entry_id,
                knowledge_id=data_model.knowledge_id,
                doc_id=data_model.doc_id,
                path=data_model.path,
                filename=data_model.path.split("/")[-1],  # Extract filename from path
                cleaned_content=clean_text(data_model.content, preserve_urls=True),
                user_id=data_model.user_id,
                image=data_model.image if data_model.image else None,
                images=data_model.images,
                type=data_model.type,
            )
        except ValidationError as e:
            print(e.json())
            raise  # Re-raise the exception after logging it
        return doc_model
