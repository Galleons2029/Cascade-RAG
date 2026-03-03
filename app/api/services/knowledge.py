"""Service helpers for knowledge base management backed by Qdrant."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.configs import qdrant_config
from app.models.knowledge import (
    ChunkCreateRequest,
    KnowledgeBase,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    KnowledgeChunk,
    KnowledgeMetadata,
)

# 使用随机 UUID 作为 metadata point ID (Qdrant 不支持字符串 ID)
ALLOWED_DISTANCES = {"cosine": "Cosine", "dot": "Dot", "euclid": "Euclid"}

METADATA_FILTER = {
    "must": [
        {
            "key": "kind",
            "match": {"value": "metadata"},
        }
    ]
}

CHUNK_FILTER = {
    "must_not": [
        {
            "key": "kind",
            "match": {"value": "metadata"},
        }
    ]
}


async def format_chunk(point: dict[str, Any]) -> KnowledgeChunk:
    """Format a Qdrant point into a KnowledgeChunk.

    Handles both the direct-API payload format (uses ``text`` key) and the
    Bytewax-pipeline format (uses ``content`` key) so that chunks created
    through either path are displayed correctly.
    """
    payload = point.get("payload") or {}

    # The pipeline stores chunk text under "content"; the direct CRUD API
    # stores it under "text".  Fall back to "content" → "chunk_content"
    # so legacy pipeline data is still readable.
    text = (
        payload.get("text")
        or payload.get("content")
        or payload.get("chunk_content")
        or ""
    )

    # Similarly, title / source may come from "filename" or "path" in
    # pipeline payloads.
    raw_title = payload.get("title") or payload.get("filename")
    raw_source = payload.get("source") or payload.get("path")

    return KnowledgeChunk(
        id=str(point.get("id")),
        text=str(text),
        title=str(raw_title) if raw_title is not None else None,
        source=str(raw_source) if raw_source is not None else None,
        tags=[str(tag) for tag in payload.get("tags", []) if isinstance(tag, str)],
        metadata=payload.get("metadata", {}) or {},
        updated_at=str(payload.get("updatedAt")) if payload.get("updatedAt") is not None else None,
    )


async def list_knowledge_bases() -> list[KnowledgeBase]:
    """Return all Qdrant collections enriched with metadata."""
    response = await _qdrant_request("GET", "/collections")
    collections = response.get("result", {}).get("collections", [])
    if not collections:
        return []

    tasks = [get_knowledge_base(item["name"]) for item in collections if item.get("name")]
    knowledge_bases = await asyncio.gather(*tasks)
    return sorted(knowledge_bases, key=lambda item: item.metadata.display_name.lower())


async def get_knowledge_base(name: str) -> KnowledgeBase:
    """Return information about a single collection."""
    normalized_name = _normalize_name(name)
    detail = await _get_collection_detail(normalized_name)
    config = detail.get("config", {})
    vector_size = _resolve_vector_size(config)
    distance = _resolve_distance(config)
    metadata = await _fetch_metadata(normalized_name)
    chunk_count = max(detail.get("points_count", 0) - (1 if metadata else 0), 0)

    return KnowledgeBase(
        name=normalized_name,
        status=detail.get("status", "unknown"),
        vector_size=vector_size,
        distance=distance,
        chunk_count=chunk_count,
        metadata=metadata or KnowledgeMetadata(display_name=normalized_name, tags=[]),
    )


async def create_knowledge_base(payload: KnowledgeBaseCreateRequest) -> KnowledgeBase:
    """Create a new Qdrant collection with optional metadata."""
    normalized_name = _normalize_name(payload.name)
    vector_config = {
        "vectors": {
            "size": payload.vector_size,
            "distance": _normalize_distance(payload.distance),
        }
    }

    await _qdrant_request(
        "PUT",
        f"/collections/{_encode_collection(normalized_name)}",
        json=vector_config,
    )

    await upsert_metadata(
        normalized_name,
        KnowledgeBaseUpdateRequest(
            display_name=payload.display_name or normalized_name,
            description=_strip_or_none(payload.description),
            tags=[],
        ),
    )

    return await get_knowledge_base(normalized_name)


async def delete_knowledge_base(name: str) -> None:
    """Delete a Qdrant collection."""
    normalized_name = _normalize_name(name)
    await _qdrant_request(
        "DELETE",
        f"/collections/{_encode_collection(normalized_name)}",
    )


async def upsert_metadata(collection: str, payload: KnowledgeBaseUpdateRequest) -> None:
    """Upsert the metadata point for a collection."""
    detail = await _get_collection_detail(collection)
    vector_size = _resolve_vector_size(detail.get("config", {}))
    point_id = str(uuid4())

    body = {
        "points": [
            {
                "id": point_id,
                "vector": _build_zero_vector(vector_size),
                "payload": {
                    "kind": "metadata",
                    "displayName": (payload.display_name or collection).strip(),
                    "description": _strip_or_none(payload.description),
                    "tags": _normalize_tags(payload.tags if payload.tags is not None else []),
                },
            }
        ]
    }

    await _qdrant_request(
        "PUT",
        f"/collections/{_encode_collection(collection)}/points",
        json=body,
    )


async def fetch_chunks(
    collection: str,
    *,
    limit: int,
    offset: str | int | None = None,
) -> tuple[list[KnowledgeChunk], str | int | None]:
    """Scroll chunk points within a collection."""
    normalized_name = _normalize_name(collection)
    payload = {
        "limit": max(1, min(limit, 200)),
        "with_payload": True,
        "with_vectors": False,
        "filter": CHUNK_FILTER,
    }
    if offset is not None:
        payload["offset"] = offset

    response = await _qdrant_request(
        "POST",
        f"/collections/{_encode_collection(normalized_name)}/points/scroll",
        json=payload,
    )
    result = response.get("result", {})
    points = result.get("points", [])
    chunks = [await format_chunk(point) for point in points]
    return chunks, result.get("next_page_offset")


async def get_chunk(collection: str, chunk_id: str) -> KnowledgeChunk | None:
    """Retrieve a single chunk."""
    normalized_name = _normalize_name(collection)
    response = await _qdrant_request(
        "POST",
        f"/collections/{_encode_collection(normalized_name)}/points/retrieve",
        json={
            "ids": [chunk_id],
            "with_payload": True,
            "with_vectors": False,
        },
    )

    points = response.get("result", {}).get("points", [])
    if not points:
        return None

    return await format_chunk(points[0])


async def delete_chunk(collection: str, chunk_id: str) -> None:
    """Delete a chunk point."""
    normalized_name = _normalize_name(collection)
    await _qdrant_request(
        "POST",
        f"/collections/{_encode_collection(normalized_name)}/points/delete",
        json={"points": [chunk_id]},
    )


async def upsert_chunk(
    collection: str,
    payload: ChunkCreateRequest,
    *,
    chunk_id: str | None = None,
) -> KnowledgeChunk:
    """Create or update a chunk point."""
    normalized_name = _normalize_name(collection)
    detail = await _get_collection_detail(normalized_name)
    vector_size = _resolve_vector_size(detail.get("config", {}))
    point_id = chunk_id or str(uuid4())

    normalized_text = _require_non_empty(payload.text)
    normalized_title = _strip_or_none(payload.title)
    normalized_source = _strip_or_none(payload.source)
    tags = _normalize_tags(payload.tags)
    metadata = payload.metadata or {}

    vector_seed = " ".join(filter(None, [normalized_title, normalized_text, point_id]))
    updated_at = datetime.now(timezone.utc).isoformat()

    body = {
        "points": [
            {
                "id": point_id,
                "payload": {
                    "kind": "chunk",
                    "text": normalized_text,
                    "title": normalized_title,
                    "source": normalized_source,
                    "tags": tags,
                    "metadata": metadata,
                    "updatedAt": updated_at,
                },
                "vector": _generate_deterministic_vector(vector_seed, vector_size),
            }
        ]
    }

    await _qdrant_request(
        "PUT",
        f"/collections/{_encode_collection(normalized_name)}/points",
        json=body,
    )

    return KnowledgeChunk(
        id=point_id,
        text=normalized_text,
        title=normalized_title,
        source=normalized_source,
        tags=tags,
        metadata=metadata,
        updated_at=updated_at,
    )


def _normalize_tags(raw_tags: Iterable[str]) -> list[str]:
    return [tag.strip() for tag in raw_tags if isinstance(tag, str) and tag.strip()]


def _require_non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Chunk 内容不能为空")
    return normalized


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="知识库名称不能为空")
    return normalized


def _normalize_distance(distance: str | None) -> str:
    if not distance:
        return "Cosine"
    normalized = distance.strip().lower()
    return ALLOWED_DISTANCES.get(normalized, "Cosine")


def _encode_collection(name: str) -> str:
    return quote(name, safe="")


async def _get_collection_detail(name: str) -> dict[str, Any]:
    response = await _qdrant_request(
        "GET",
        f"/collections/{_encode_collection(name)}",
    )
    return response.get("result", {})


async def _fetch_metadata(collection: str) -> KnowledgeMetadata | None:
    response = await _qdrant_request(
        "POST",
        f"/collections/{_encode_collection(collection)}/points/scroll",
        json={
            "limit": 1,
            "with_payload": True,
            "with_vectors": False,
            "filter": METADATA_FILTER,
        },
    )

    points = response.get("result", {}).get("points", [])
    if not points:
        return None

    payload = points[0].get("payload") or {}
    display_name = payload.get("displayName") or payload.get("metadata", {}).get("displayName") or collection
    description = payload.get("description") or payload.get("metadata", {}).get("description")
    tags = payload.get("tags") or payload.get("metadata", {}).get("tags") or []

    return KnowledgeMetadata(
        display_name=str(display_name),
        description=str(description) if description is not None else None,
        tags=[str(tag) for tag in tags if isinstance(tag, str)],
    )


def _resolve_vector_size(config: dict[str, Any]) -> int:
    params = config.get("params", {})
    vectors = params.get("vectors")
    if isinstance(vectors, int):
        return vectors

    if isinstance(vectors, dict):
        if "size" in vectors:
            return int(vectors["size"])
        first = next((value for value in vectors.values() if isinstance(value, dict) and "size" in value), None)
        if first:
            return int(first["size"])

    raise HTTPException(status_code=500, detail="无法确定集合的向量维度")


def _resolve_distance(config: dict[str, Any]) -> str | None:
    params = config.get("params", {})
    vectors = params.get("vectors")
    if isinstance(vectors, dict):
        if "distance" in vectors:
            return str(vectors["distance"])
        first = next((value for value in vectors.values() if isinstance(value, dict) and "distance" in value), None)
        if first:
            return str(first["distance"])
    return None


def _build_zero_vector(dimension: int) -> list[float]:
    if dimension <= 0:
        raise HTTPException(status_code=400, detail="向量维度必须为正数")
    return [0.0] * dimension


def _generate_deterministic_vector(seed: str, dimension: int) -> list[float]:
    if dimension <= 0:
        raise HTTPException(status_code=400, detail="向量维度必须为正数")
    vector = [0.0] * dimension
    if not seed:
        return vector
    for index, char in enumerate(seed):
        bucket = index % dimension
        vector[bucket] += (ord(char) % 97) / 97.0
    total = sum(vector)
    if total == 0:
        return vector
    return [value / total for value in vector]


async def _qdrant_request(method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
    base_url = _resolve_qdrant_base_url()
    url = path if path.startswith(("http://", "https://")) else f"{base_url}{path}"
    headers = {"content-type": "application/json"}
    if qdrant_config.QDRANT_APIKEY:
        headers["api-key"] = qdrant_config.QDRANT_APIKEY

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, json=json, headers=headers)
    except httpx.RequestError as exc:  # pragma: no cover - network failure
        raise HTTPException(status_code=503, detail=f"无法连接 Qdrant 服务: {exc}") from exc

    if response.status_code >= 400:
        message = _extract_error(response)
        raise HTTPException(status_code=response.status_code, detail=message)

    if response.status_code == 204:
        return None

    return response.json()


def _resolve_qdrant_base_url() -> str:
    if qdrant_config.USE_QDRANT_CLOUD and qdrant_config.QDRANT_CLOUD_URL:
        return qdrant_config.QDRANT_CLOUD_URL.rstrip("/")

    host = qdrant_config.QDRANT_DATABASE_HOST or "127.0.0.1"
    if host.startswith(("http://", "https://")):
        return host.rstrip("/")

    port = qdrant_config.QDRANT_DATABASE_PORT or 6333
    return f"http://{host}:{port}"


def _extract_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:  # pragma: no cover - non json error
        return response.text or "未知错误"

    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return payload.get("status", {}).get("error") or payload.get("error") or payload.get("detail") or response.reason_phrase
    return response.reason_phrase
