from typing import Optional

from app.pipeline.feature_pipeline.models.base import DataModel


class RepositoryRawModel(DataModel):
    name: str
    link: str
    content: dict
    owner_id: str


class ArticleRawModel(DataModel):
    platform: str
    link: str
    content: dict
    author_id: str


class PostsRawModel(DataModel):
    platform: str
    content: dict
    author_id: str | None = None
    image: Optional[str] = None


class DocumentRawModel(DataModel):
    knowledge_id: str
    doc_id: str
    path: str
    filename: str
    content: str
    user_id: str | None = None
    image: Optional[str] = None
    images: Optional[list[dict]] = None
