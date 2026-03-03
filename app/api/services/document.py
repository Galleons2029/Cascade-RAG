# -*- coding: utf-8 -*-
# @Time    : 2025/01/13
# @Author  : Galleons
# @File    : document.py

"""
文档上传与解析服务
集成 MinerU API 实现文档解析，通过 RabbitMQ 队列将解析结果载入 Qdrant
"""

from __future__ import annotations

import asyncio
import io
import os
import zipfile
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.services.mineru import mineru_service
from app.api.services.markdown_image_enricher import (
    enrich_markdown,
    extract_markdown_and_assets,
)
from app.core import logger_utils
from app.core.mq import publish_to_rabbitmq
from app.pipeline.feature_pipeline.models.raw import DocumentRawModel

logger = logger_utils.get_logger(__name__)

# 支持的文件类型
SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg",
    ".txt", ".md", ".markdown",
    ".csv", ".json",
}

# 最大文件大小 (200MB)
MAX_FILE_SIZE = 200 * 1024 * 1024

# RabbitMQ 队列名称
DOCUMENT_QUEUE_NAME = "test_files"


class DocumentUploadTask:
    """文档上传任务模型"""

    def __init__(
        self,
        task_id: str,
        collection: str,
        filename: str,
        status: str = "pending",
        mineru_task_id: str | None = None,
        error_message: str | None = None,
        created_at: str | None = None,
        progress: dict[str, Any] | None = None,
    ):
        self.task_id = task_id
        self.collection = collection
        self.filename = filename
        self.status = status
        self.mineru_task_id = mineru_task_id
        self.error_message = error_message
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.progress = progress or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "collection": self.collection,
            "filename": self.filename,
            "status": self.status,
            "mineruTaskId": self.mineru_task_id,
            "errorMessage": self.error_message,
            "createdAt": self.created_at,
            "progress": self.progress,
        }


# 内存中存储任务状态（生产环境应使用 Redis/数据库）
_upload_tasks: dict[str, DocumentUploadTask] = {}


def validate_file(file: UploadFile) -> None:
    """验证上传的文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}。支持的类型: {', '.join(SUPPORTED_EXTENSIONS)}",
        )


async def read_file_content(file: UploadFile) -> bytes:
    """读取文件内容并验证大小"""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)",
        )
    return content


def _publish_to_queue(
    collection: str,
    filename: str,
    content: str,
    doc_id: str | None = None,
    images: list[dict] | None = None,
) -> None:
    """
    将解析后的内容发送到 RabbitMQ 队列

    Args:
        collection: 知识库名称（对应 Qdrant collection）
        filename: 文件名
        content: 解析后的文本内容
        doc_id: 文档 ID
        images: 图片元数据列表
    """
    data = DocumentRawModel(
        knowledge_id=collection,
        doc_id=doc_id or str(uuid4()),
        path=filename,
        filename=filename,
        content=content,
        type="documents",
        entry_id=str(uuid4()),
        images=images,
    ).model_dump_json()

    publish_to_rabbitmq(queue_name=DOCUMENT_QUEUE_NAME, data=data)
    logger.info(f"已将文档发送到队列: {filename} -> {collection}")


async def upload_document_to_collection(
    collection: str,
    file: UploadFile,
    *,
    use_mineru: bool = True,
    model_version: str = "vlm",
) -> DocumentUploadTask:
    """
    上传文档到知识库

    Args:
        collection: 知识库名称
        file: 上传的文件
        use_mineru: 是否使用 MinerU 解析
        model_version: MinerU 模型版本

    Returns:
        上传任务信息
    """
    validate_file(file)

    task_id = str(uuid4())
    filename = file.filename or "unknown"

    task = DocumentUploadTask(
        task_id=task_id,
        collection=collection,
        filename=filename,
        status="uploading",
    )
    _upload_tasks[task_id] = task

    try:
        content = await read_file_content(file)
        ext = os.path.splitext(filename)[1].lower()

        if use_mineru and ext in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}:
            # 使用 MinerU 解析复杂文档
            await _process_with_mineru(task, content, model_version)
        else:
            # 直接处理文本文件
            await _process_text_file(task, content, ext)

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        logger.error("文档上传失败", task_id=task_id, error=str(e))

    return task


async def _process_with_mineru(
    task: DocumentUploadTask,
    content: bytes,
    model_version: str,
) -> None:
    """使用 MinerU 处理文档"""
    task.status = "processing"

    try:
        # 申请上传链接
        data_id = f"{task.collection}_{task.task_id}"
        upload_result = await mineru_service.create_batch_upload_urls(
            files=[{"name": task.filename, "data_id": data_id}],
            model_version=model_version,
        )

        batch_id = upload_result.get("batch_id")
        file_urls = upload_result.get("file_urls", [])

        if not file_urls:
            raise Exception("获取上传链接失败")

        # 上传文件到 MinerU
        upload_success = await mineru_service.upload_file_to_presigned_url(
            file_urls[0],
            content,
        )

        if not upload_success:
            raise Exception("文件上传到 MinerU 失败")

        task.mineru_task_id = batch_id
        task.status = "parsing"

        # 启动后台任务等待解析完成
        asyncio.create_task(_wait_and_process_mineru_result(task))

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        raise


async def _wait_and_process_mineru_result(task: DocumentUploadTask) -> None:
    """等待 MinerU 解析完成并处理结果"""
    try:
        batch_id = task.mineru_task_id
        if not batch_id:
            return

        # 轮询等待解析完成
        max_attempts = 200  # 最多等待 10 分钟
        for attempt in range(max_attempts):
            result = await mineru_service.get_batch_results(batch_id)
            extract_results = result.get("extract_result", [])

            if not extract_results:
                await asyncio.sleep(3)
                continue

            file_result = extract_results[0]
            state = file_result.get("state")

            if state == "done":
                # 下载并处理结果
                zip_url = file_result.get("full_zip_url")
                if zip_url:
                    await _download_and_publish_result(task, zip_url)
                task.status = "completed"
                return

            elif state == "failed":
                task.status = "failed"
                task.error_message = file_result.get("err_msg", "解析失败")
                return

            elif state in ("pending", "running", "converting", "waiting-file"):
                progress = file_result.get("extract_progress", {})
                task.progress = {
                    "state": state,
                    "extractedPages": progress.get("extracted_pages", 0),
                    "totalPages": progress.get("total_pages", 0),
                }
                await asyncio.sleep(3)

            else:
                await asyncio.sleep(3)

        task.status = "failed"
        task.error_message = "解析超时"

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        logger.error("处理 MinerU 结果失败", task_id=task.task_id, error=str(e))


async def _download_and_publish_result(task: DocumentUploadTask, zip_url: str) -> None:
    """下载解析结果，进行图片理解后通过 RabbitMQ 发送到队列"""
    try:
        # 下载 ZIP 文件
        zip_content = await mineru_service.download_result_zip(zip_url)

        # 解压并提取 Markdown + 图片资产
        markdown_content, assets_map = extract_markdown_and_assets(zip_content)

        if not markdown_content:
            # 降级：尝试旧方式提取纯文本
            markdown_content = _extract_markdown_from_zip(zip_content)

        if markdown_content:
            # 图片理解 + 重写 markdown
            try:
                enriched_content, images_metadata = await enrich_markdown(
                    markdown_text=markdown_content,
                    assets_map=assets_map,
                    doc_id=task.task_id,
                )
            except Exception as e:
                logger.warning(
                    "图片处理失败，降级使用原始 markdown",
                    task_id=task.task_id,
                    error=str(e),
                )
                enriched_content = markdown_content
                images_metadata = None

            # 将处理后的内容发送到 RabbitMQ 队列
            await run_in_threadpool(
                _publish_to_queue,
                task.collection,
                task.filename,
                enriched_content,
                task.task_id,
                images_metadata,
            )

            logger.info(
                "文档解析完成并发送到队列",
                task_id=task.task_id,
                filename=task.filename,
                content_length=len(enriched_content),
                images_count=len(images_metadata) if images_metadata else 0,
            )
        else:
            raise Exception("无法提取文档内容")

    except Exception as e:
        logger.error("下载或发布解析结果失败", task_id=task.task_id, error=str(e))
        raise


def _extract_markdown_from_zip(zip_content: bytes) -> str:
    """从 ZIP 文件中提取 Markdown 内容"""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            # 查找 Markdown 文件
            for name in zf.namelist():
                if name.endswith(".md"):
                    return zf.read(name).decode("utf-8", errors="ignore")

            # 如果没有 MD 文件，尝试读取 JSON 内容
            for name in zf.namelist():
                if name.endswith(".json") and "content" in name.lower():
                    import json
                    content = json.loads(zf.read(name).decode("utf-8"))
                    if isinstance(content, dict) and "text" in content:
                        return content["text"]

    except Exception as e:
        logger.error("解压 ZIP 文件失败", error=str(e))

    return ""


async def _process_text_file(
    task: DocumentUploadTask,
    content: bytes,
    ext: str,
) -> None:
    """处理文本文件，直接发送到 RabbitMQ 队列"""
    task.status = "processing"

    try:
        text = content.decode("utf-8", errors="ignore")

        if not text.strip():
            raise Exception("文件内容为空")

        # 发送到 RabbitMQ 队列
        await run_in_threadpool(
            _publish_to_queue,
            task.collection,
            task.filename,
            text,
            task.task_id,
        )

        task.status = "completed"
        logger.info(
            "文本文件发送到队列完成",
            task_id=task.task_id,
            filename=task.filename,
            content_length=len(text),
        )

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        raise


def get_upload_task(task_id: str) -> DocumentUploadTask | None:
    """获取上传任务状态"""
    return _upload_tasks.get(task_id)


def list_upload_tasks(collection: str | None = None) -> list[DocumentUploadTask]:
    """列出上传任务"""
    tasks = list(_upload_tasks.values())
    if collection:
        tasks = [t for t in tasks if t.collection == collection]
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


def clear_completed_tasks() -> int:
    """清理已完成的任务"""
    global _upload_tasks
    completed = [k for k, v in _upload_tasks.items() if v.status in ("completed", "failed")]
    for k in completed:
        del _upload_tasks[k]
    return len(completed)
