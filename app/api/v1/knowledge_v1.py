"""Knowledge base management API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.services import knowledge as knowledge_service
from app.api.services import document as document_service
from app.models.knowledge import (
    ChunkCreateRequest,
    ChunkListResponse,
    ChunkResponse,
    ChunkUpdateRequest,
    DocumentUploadListResponse,
    DocumentUploadResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
    KnowledgeStats,
    KnowledgeStatsResponse,
    SuccessResponse,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/collections", response_model=KnowledgeBaseListResponse)
async def list_collections() -> KnowledgeBaseListResponse:
    data = await knowledge_service.list_knowledge_bases()
    return KnowledgeBaseListResponse(data=data)


@router.post(
    "/collections",
    response_model=KnowledgeBaseResponse,
    status_code=201,
)
async def create_collection(
    payload: KnowledgeBaseCreateRequest,
) -> KnowledgeBaseResponse:
    data = await knowledge_service.create_knowledge_base(payload)
    return KnowledgeBaseResponse(data=data)


@router.get(
    "/collections/{collection}",
    response_model=KnowledgeBaseResponse,
)
async def get_collection(collection: str) -> KnowledgeBaseResponse:
    data = await knowledge_service.get_knowledge_base(collection)
    return KnowledgeBaseResponse(data=data)


@router.patch(
    "/collections/{collection}",
    response_model=KnowledgeBaseResponse,
)
async def update_collection(
    collection: str,
    payload: KnowledgeBaseUpdateRequest,
) -> KnowledgeBaseResponse:
    if payload.display_name is None and payload.description is None and payload.tags is None:
        raise HTTPException(status_code=400, detail="请至少提供一个需要更新的字段")

    await knowledge_service.upsert_metadata(collection, payload)
    data = await knowledge_service.get_knowledge_base(collection)
    return KnowledgeBaseResponse(data=data)


@router.delete(
    "/collections/{collection}",
    response_model=SuccessResponse,
)
async def delete_collection(collection: str) -> SuccessResponse:
    await knowledge_service.delete_knowledge_base(collection)
    return SuccessResponse(success=True)


@router.get(
    "/collections/{collection}/chunks",
    response_model=ChunkListResponse,
)
async def list_chunks(
    collection: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: str | int | None = Query(default=None),
) -> ChunkListResponse:
    chunks, next_offset = await knowledge_service.fetch_chunks(
        collection,
        limit=limit,
        offset=offset,
    )
    return ChunkListResponse(data=chunks, next_offset=next_offset)


@router.post(
    "/collections/{collection}/chunks",
    response_model=ChunkResponse,
    status_code=201,
)
async def create_chunk(
    collection: str,
    payload: ChunkCreateRequest,
) -> ChunkResponse:
    chunk = await knowledge_service.upsert_chunk(collection, payload)
    return ChunkResponse(data=chunk)


@router.get(
    "/collections/{collection}/chunks/{chunk_id}",
    response_model=ChunkResponse,
)
async def get_chunk(collection: str, chunk_id: str) -> ChunkResponse:
    chunk = await knowledge_service.get_chunk(collection, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="未找到指定 Chunk")
    return ChunkResponse(data=chunk)


@router.patch(
    "/collections/{collection}/chunks/{chunk_id}",
    response_model=ChunkResponse,
)
async def update_chunk(
    collection: str,
    chunk_id: str,
    payload: ChunkUpdateRequest,
) -> ChunkResponse:
    existing = await knowledge_service.get_chunk(collection, chunk_id)
    if not existing:
        raise HTTPException(status_code=404, detail="未找到指定 Chunk")

    merged_payload = ChunkCreateRequest(
        text=payload.text or existing.text,
        title=payload.title if payload.title is not None else existing.title,
        source=payload.source if payload.source is not None else existing.source,
        tags=payload.tags if payload.tags is not None else (existing.tags or []),
        metadata=payload.metadata if payload.metadata is not None else existing.metadata or {},
    )

    chunk = await knowledge_service.upsert_chunk(collection, merged_payload, chunk_id=chunk_id)
    return ChunkResponse(data=chunk)


@router.delete(
    "/collections/{collection}/chunks/{chunk_id}",
    response_model=SuccessResponse,
)
async def delete_chunk(collection: str, chunk_id: str) -> SuccessResponse:
    await knowledge_service.delete_chunk(collection, chunk_id)
    return SuccessResponse(success=True)


# ==================== 统计接口 ====================

@router.get("/stats", response_model=KnowledgeStatsResponse)
async def get_stats() -> KnowledgeStatsResponse:
    """获取知识库统计信息"""
    knowledge_bases = await knowledge_service.list_knowledge_bases()
    total_chunks = sum(kb.chunk_count for kb in knowledge_bases)
    return KnowledgeStatsResponse(
        data=KnowledgeStats(
            total_collections=len(knowledge_bases),
            total_chunks=total_chunks,
        )
    )


# ==================== 文档上传接口 ====================

@router.post(
    "/collections/{collection}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    collection: str,
    file: UploadFile = File(...),
    use_mineru: bool = Form(default=True),
    model_version: str = Form(default="vlm"),
) -> DocumentUploadResponse:
    """
    上传文档到知识库

    - **collection**: 目标知识库名称
    - **file**: 上传的文件（支持 PDF、Word、PPT、图片、文本等格式）
    - **use_mineru**: 是否使用 MinerU 进行文档解析
    - **model_version**: MinerU 模型版本 (pipeline/vlm)
    """
    task = await document_service.upload_document_to_collection(
        collection,
        file,
        use_mineru=use_mineru,
        model_version=model_version,
    )
    return DocumentUploadResponse(
        task_id=task.task_id,
        collection=task.collection,
        filename=task.filename,
        status=task.status,
        mineru_task_id=task.mineru_task_id,
        error_message=task.error_message,
        created_at=task.created_at,
        progress=task.progress,
    )


@router.get(
    "/collections/{collection}/documents/tasks",
    response_model=DocumentUploadListResponse,
)
async def list_document_tasks(collection: str) -> DocumentUploadListResponse:
    """获取知识库的文档上传任务列表"""
    tasks = document_service.list_upload_tasks(collection)
    return DocumentUploadListResponse(
        data=[
            DocumentUploadResponse(
                task_id=t.task_id,
                collection=t.collection,
                filename=t.filename,
                status=t.status,
                mineru_task_id=t.mineru_task_id,
                error_message=t.error_message,
                created_at=t.created_at,
                progress=t.progress,
            )
            for t in tasks
        ]
    )


@router.get(
    "/documents/tasks/{task_id}",
    response_model=DocumentUploadResponse,
)
async def get_document_task(task_id: str) -> DocumentUploadResponse:
    """获取文档上传任务状态"""
    task = document_service.get_upload_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="未找到指定任务")
    return DocumentUploadResponse(
        task_id=task.task_id,
        collection=task.collection,
        filename=task.filename,
        status=task.status,
        mineru_task_id=task.mineru_task_id,
        error_message=task.error_message,
        created_at=task.created_at,
        progress=task.progress,
    )


# ==================== 静态图片资产接口 ====================

# 图片存储根目录（与 markdown_image_enricher 一致）
_ASSETS_ROOT = Path(__file__).resolve().parents[3] / "uploads" / "mineru_assets"

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


@router.get("/assets/{doc_id}/{asset_path:path}")
async def serve_asset(doc_id: str, asset_path: str):
    """
    提供文档图片静态资源访问。

    安全控制：禁止 .. / 绝对路径 / 越界访问
    """
    # 安全检查
    if ".." in asset_path or asset_path.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="非法路径")

    file_path = (_ASSETS_ROOT / doc_id / asset_path).resolve()

    # 确保路径在 ASSETS_ROOT 内
    if not str(file_path).startswith(str(_ASSETS_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    suffix = file_path.suffix.lower()
    media_type = _IMAGE_MEDIA_TYPES.get(suffix, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)
