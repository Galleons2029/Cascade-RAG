# -*- coding: utf-8 -*-
# @Time    : 2025/01/13
# @Author  : Galleons
# @File    : mineru.py

"""
MinerU 文档解析服务
基于 MinerU API 实现文档解析功能
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from datetime import datetime

import httpx

from app.core import logger_utils
from dotenv import load_dotenv

# 确保加载 .env 文件
load_dotenv()

logger = logger_utils.get_logger(__name__)

MINERU_BASE_URL = "https://mineru.net/api/v4"
MINERU_API_TOKEN = os.getenv("MINERU_API_KEY") or ""


class MineruService:
    """MinerU 文档解析服务类"""

    def __init__(self, token: str | None = None):
        self.token = token or MINERU_API_TOKEN
        self.base_url = MINERU_BASE_URL
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """发送 HTTP 请求到 MinerU API"""
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{self.base_url}{path}"
            response = await client.request(
                method,
                url,
                headers=self.headers,
                json=json,
            )

            if response.status_code != 200:
                logger.error(
                    "MinerU API 请求失败",
                    status_code=response.status_code,
                    response=response.text,
                )
                raise Exception(f"MinerU API 错误: {response.text}")

            return response.json()

    async def create_parse_task(
        self,
        url: str,
        *,
        model_version: str = "vlm",
        data_id: str | None = None,
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        extra_formats: list[str] | None = None,
        page_ranges: str | None = None,
    ) -> dict[str, Any]:
        """
        创建单个文件解析任务

        Args:
            url: 文件 URL
            model_version: 模型版本 (pipeline/vlm)
            data_id: 业务数据 ID
            is_ocr: 是否启用 OCR
            enable_formula: 是否开启公式识别
            enable_table: 是否开启表格识别
            language: 文档语言
            extra_formats: 额外导出格式 (docx/html/latex)
            page_ranges: 指定页码范围

        Returns:
            包含 task_id 的响应
        """
        payload: dict[str, Any] = {
            "url": url,
            "model_version": model_version,
        }

        if data_id:
            payload["data_id"] = data_id
        if is_ocr:
            payload["is_ocr"] = is_ocr
        if not enable_formula:
            payload["enable_formula"] = enable_formula
        if not enable_table:
            payload["enable_table"] = enable_table
        if language != "ch":
            payload["language"] = language
        if extra_formats:
            payload["extra_formats"] = extra_formats
        if page_ranges:
            payload["page_ranges"] = page_ranges

        result = await self._request("POST", "/extract/task", json=payload)

        if result.get("code") != 0:
            raise Exception(f"创建解析任务失败: {result.get('msg')}")

        return result.get("data", {})

    async def get_task_result(self, task_id: str) -> dict[str, Any]:
        """
        获取解析任务结果

        Args:
            task_id: 任务 ID

        Returns:
            任务结果信息
        """
        result = await self._request("GET", f"/extract/task/{task_id}")

        if result.get("code") != 0:
            raise Exception(f"获取任务结果失败: {result.get('msg')}")

        return result.get("data", {})

    async def create_batch_upload_urls(
        self,
        files: list[dict[str, Any]],
        *,
        model_version: str = "vlm",
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        extra_formats: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        批量申请文件上传链接

        Args:
            files: 文件列表 [{"name": "demo.pdf", "data_id": "xxx"}, ...]
            model_version: 模型版本
            enable_formula: 是否开启公式识别
            enable_table: 是否开启表格识别
            language: 文档语言
            extra_formats: 额外导出格式

        Returns:
            包含 batch_id 和 file_urls 的响应
        """
        payload: dict[str, Any] = {
            "files": files,
            "model_version": model_version,
        }

        if not enable_formula:
            payload["enable_formula"] = enable_formula
        if not enable_table:
            payload["enable_table"] = enable_table
        if language != "ch":
            payload["language"] = language
        if extra_formats:
            payload["extra_formats"] = extra_formats

        result = await self._request("POST", "/file-urls/batch", json=payload)

        if result.get("code") != 0:
            raise Exception(f"申请上传链接失败: {result.get('msg')}")

        return result.get("data", {})

    async def upload_file_to_presigned_url(
        self,
        presigned_url: str,
        file_content: bytes,
    ) -> bool:
        """
        上传文件到预签名 URL

        Args:
            presigned_url: 预签名上传 URL
            file_content: 文件内容

        Returns:
            上传是否成功
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.put(presigned_url, content=file_content)
            return response.status_code == 200

    async def create_batch_url_tasks(
        self,
        files: list[dict[str, Any]],
        *,
        model_version: str = "vlm",
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        extra_formats: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        批量创建 URL 解析任务

        Args:
            files: 文件列表 [{"url": "https://...", "data_id": "xxx"}, ...]
            model_version: 模型版本
            enable_formula: 是否开启公式识别
            enable_table: 是否开启表格识别
            language: 文档语言
            extra_formats: 额外导出格式

        Returns:
            包含 batch_id 的响应
        """
        payload: dict[str, Any] = {
            "files": files,
            "model_version": model_version,
        }

        if not enable_formula:
            payload["enable_formula"] = enable_formula
        if not enable_table:
            payload["enable_table"] = enable_table
        if language != "ch":
            payload["language"] = language
        if extra_formats:
            payload["extra_formats"] = extra_formats

        result = await self._request("POST", "/extract/task/batch", json=payload)

        if result.get("code") != 0:
            raise Exception(f"批量创建任务失败: {result.get('msg')}")

        return result.get("data", {})

    async def get_batch_results(self, batch_id: str) -> dict[str, Any]:
        """
        批量获取任务结果

        Args:
            batch_id: 批量任务 ID

        Returns:
            批量任务结果信息
        """
        result = await self._request("GET", f"/extract-results/batch/{batch_id}")

        if result.get("code") != 0:
            raise Exception(f"获取批量结果失败: {result.get('msg')}")

        return result.get("data", {})

    async def wait_for_task_completion(
        self,
        task_id: str,
        *,
        poll_interval: float = 3.0,
        max_wait_time: float = 600.0,
    ) -> dict[str, Any]:
        """
        等待任务完成

        Args:
            task_id: 任务 ID
            poll_interval: 轮询间隔（秒）
            max_wait_time: 最大等待时间（秒）

        Returns:
            完成后的任务结果
        """
        start_time = datetime.now()

        while True:
            result = await self.get_task_result(task_id)
            state = result.get("state")

            if state == "done":
                return result
            elif state == "failed":
                raise Exception(f"解析任务失败: {result.get('err_msg')}")
            elif state in ("pending", "running", "converting"):
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > max_wait_time:
                    raise Exception(f"等待任务完成超时: {task_id}")

                logger.info(
                    "等待解析任务完成",
                    task_id=task_id,
                    state=state,
                    elapsed=elapsed,
                )
                await asyncio.sleep(poll_interval)
            else:
                raise Exception(f"未知任务状态: {state}")

    async def download_result_zip(self, zip_url: str) -> bytes:
        """
        下载解析结果压缩包

        Args:
            zip_url: 压缩包 URL

        Returns:
            压缩包内容
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(zip_url)
            if response.status_code != 200:
                raise Exception(f"下载结果失败: {response.status_code}")
            return response.content


# 全局服务实例
mineru_service = MineruService()
