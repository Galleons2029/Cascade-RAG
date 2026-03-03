from typing import Tuple

import numpy as np

from app.pipeline.feature_pipeline.models.base import VectorDBDataModel


class PostEmbeddedChunkModel(VectorDBDataModel):
    entry_id: str
    platform: str
    chunk_id: str
    chunk_content: str
    embedded_content: np.ndarray
    author_id: str
    type: str

    class Config:
        arbitrary_types_allowed = True

    def to_payload(self) -> Tuple[str, np.ndarray, dict]:
        data = {
            "id": self.entry_id,
            "platform": self.platform,
            "content": self.chunk_content,
            "owner_id": self.author_id,
            "type": self.type,
        }

        return self.chunk_id, self.embedded_content, data


class ArticleEmbeddedChunkModel(VectorDBDataModel):
    entry_id: str
    platform: str
    link: str
    chunk_id: str
    chunk_content: str
    embedded_content: np.ndarray
    author_id: str
    type: str

    class Config:
        arbitrary_types_allowed = True

    def to_payload(self) -> Tuple[str, np.ndarray, dict]:
        data = {
            "id": self.entry_id,
            "platform": self.platform,
            "content": self.chunk_content,
            "link": self.link,
            "author_id": self.author_id,
            "type": self.type,
        }

        return self.chunk_id, self.embedded_content, data


class RepositoryEmbeddedChunkModel(VectorDBDataModel):
    entry_id: str
    name: str
    link: str
    chunk_id: str
    chunk_content: str
    embedded_content: np.ndarray
    owner_id: str
    type: str

    class Config:
        arbitrary_types_allowed = True

    def to_payload(self) -> Tuple[str, np.ndarray, dict]:
        data = {
            "id": self.entry_id,
            "name": self.name,
            "content": self.chunk_content,
            "link": self.link,
            "owner_id": self.owner_id,
            "type": self.type,
        }

        return self.chunk_id, self.embedded_content, data


class DocumentEmbeddedChunkModel(VectorDBDataModel):
    entry_id: str
    knowledge_id: str
    doc_id: str
    path: str
    filename: str
    chunk_id: str
    chunk_content: str
    # hybrid_vec: dict
    embedded_content: np.ndarray
    user_id: str | None = None
    images: list[dict] | None = None
    type: str

    class Config:
        arbitrary_types_allowed = True

    def to_payload(self) -> Tuple[str, dict, dict]:
        data = {
            "kind": "chunk",
            "knowledge_id": self.knowledge_id,
            "doc_id": self.doc_id,
            "path": self.path,
            "filename": self.filename,
            "user_id": self.user_id,
            # Keep "content" for backward compat; add "text" so the
            # knowledge API can read it directly without fallback.
            "content": self.chunk_content,
            "text": self.chunk_content,
            "title": self.filename,
            "source": self.path,
            "type": self.type,
        }
        if self.images:
            data["images"] = self.images

        return self.chunk_id, self.embedded_content, data
        # return self.chunk_id, self.hybrid_vec, data
