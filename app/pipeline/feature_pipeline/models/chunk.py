from typing import Optional

from app.pipeline.feature_pipeline.models.base import DataModel


class PostChunkModel(DataModel):
    entry_id: str
    platform: str
    chunk_id: str
    chunk_content: str
    author_id: str
    image: Optional[str] = None
    type: str


class ArticleChunkModel(DataModel):
    entry_id: str
    platform: str
    link: str
    chunk_id: str
    chunk_content: str
    author_id: str
    type: str


class RepositoryChunkModel(DataModel):
    entry_id: str
    name: str
    link: str
    chunk_id: str
    chunk_content: str
    owner_id: str
    type: str


class DocumentChunkModel(DataModel):
    entry_id: str
    knowledge_id: str
    doc_id: str
    filename: str
    path: str
    chunk_id: str
    chunk_content: str
    user_id: str | None = None
    image: Optional[str] = None
    images: Optional[list[dict]] = None
    type: str
