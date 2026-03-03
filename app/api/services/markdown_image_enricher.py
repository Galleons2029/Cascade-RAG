# -*- coding: utf-8 -*-
"""
Markdown 图片统一处理器（入队前）

功能：
1. 从 MinerU ZIP 中提取 markdown 与图片资产
2. 将图片 URL 规范化为可访问 URL（相对路径落盘后映射）
3. 调用多模态 VLM 生成图片描述（caption）
4. 重写 markdown：保留图片 + 追加描述文本，方便向量检索
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import httpx

from app.configs.llm_config import settings as llm_settings
from app.core import logger_utils

logger = logger_utils.get_logger(__name__)

# 图片存储根目录
ASSETS_ROOT = Path(__file__).resolve().parents[3] / "uploads" / "mineru_assets"

# Markdown 图片标签正则  ![alt](url)
_IMG_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# 1. ZIP 提取
# ---------------------------------------------------------------------------

def extract_markdown_and_assets(zip_bytes: bytes) -> tuple[str, dict[str, bytes]]:
    """
    从 MinerU 输出的 ZIP 中提取 markdown 文本和图片资产映射。

    Returns:
        (markdown_text, assets_map)
        assets_map: { 相对路径 -> 文件 bytes }
    """
    markdown_text = ""
    assets_map: dict[str, bytes] = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".md"):
                markdown_text = zf.read(name).decode("utf-8", errors="ignore")
            elif _is_image_file(lower):
                assets_map[name] = zf.read(name)

    return markdown_text, assets_map


def _is_image_file(name: str) -> bool:
    return any(name.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"))


# ---------------------------------------------------------------------------
# 2. 图片 URL 规范化
# ---------------------------------------------------------------------------

def save_asset_to_disk(doc_id: str, relative_path: str, data: bytes) -> Path:
    """将图片资产保存到本地磁盘，返回保存后的绝对路径。"""
    safe_path = _sanitize_path(relative_path)
    dest = ASSETS_ROOT / doc_id / safe_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def resolve_image_url(
    raw_url: str,
    assets_map: dict[str, bytes],
    doc_id: str,
    base_url: str | None = None,
) -> str | None:
    """
    将 markdown 中的图片 URL 规范化为可访问 URL。

    - http/https URL：直接返回
    - 相对路径：从 assets_map 落盘后生成公开 URL
    """
    if raw_url.startswith(("http://", "https://")):
        return raw_url

    # 相对路径 -> 从 assets_map 找到对应资产并落盘
    matched_key = _find_asset_key(raw_url, assets_map)
    if matched_key is None:
        logger.warning("图片资产未找到", raw_url=raw_url, doc_id=doc_id)
        return None

    save_asset_to_disk(doc_id, matched_key, assets_map[matched_key])
    safe_path = _sanitize_path(matched_key)
    backend_base = (base_url or llm_settings.PUBLIC_BACKEND_BASE_URL).rstrip("/")
    return f"{backend_base}/api/v1/knowledge/assets/{doc_id}/{safe_path}"


def _find_asset_key(raw_url: str, assets_map: dict[str, bytes]) -> str | None:
    """在 assets_map 中匹配图片路径（支持前缀 ./ 和部分路径匹配）。"""
    normalized = raw_url.lstrip("./")
    for key in assets_map:
        if key == raw_url or key.endswith(normalized) or normalized.endswith(key):
            return key
    return None


def _sanitize_path(path: str) -> str:
    """清理路径，防止目录穿越。"""
    # 去除 .. 和绝对路径前缀
    parts = Path(path).parts
    safe_parts = [p for p in parts if p not in ("..", "/", "\\")]
    return str(Path(*safe_parts)) if safe_parts else "unknown"


# ---------------------------------------------------------------------------
# 3. VLM 图片描述
# ---------------------------------------------------------------------------

async def caption_image(image_url: str) -> str:
    """
    调用 VLM 生成图片描述。
    使用 OpenAI 兼容接口（如硅基流动）。
    """
    try:
        api_key = llm_settings.SILICON_KEY or llm_settings.API_KEY
        base_url = (llm_settings.SILICON_BASE_URL or "https://api.siliconflow.cn/v1").rstrip("/")

        payload = {
            "model": llm_settings.VISION_CAPTION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": llm_settings.VISION_CAPTION_PROMPT},
                    ],
                }
            ],
            "max_tokens": 512,
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=llm_settings.VISION_CAPTION_TIMEOUT_SEC) as client:
            for attempt in range(llm_settings.VISION_CAPTION_MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    caption = data["choices"][0]["message"]["content"].strip()
                    # 去除可能的 think 标签
                    caption = re.sub(r"<think>.*?</think>", "", caption, flags=re.DOTALL).strip()
                    return caption
                except (httpx.HTTPStatusError, httpx.ReadTimeout, KeyError) as e:
                    if attempt < llm_settings.VISION_CAPTION_MAX_RETRIES:
                        logger.warning("图片描述重试", attempt=attempt + 1, url=image_url, error=str(e))
                        await asyncio.sleep(1 * (attempt + 1))
                    else:
                        raise

    except Exception as e:
        logger.error("图片描述生成失败", url=image_url, error=str(e))
        return "图片解析失败"


# ---------------------------------------------------------------------------
# 4. Markdown 重写
# ---------------------------------------------------------------------------

def rewrite_markdown_images(
    markdown_text: str,
    mapping: dict[str, dict[str, str]],
) -> str:
    """
    重写 markdown 中的图片标签。

    mapping: { original_url: { "resolved_url": str, "caption": str } }

    输出规则（每个图片）：
      ![<caption>](<resolved_url>)
      图片描述：<caption>（图片URL：<resolved_url>）
    """

    def _replace(match: re.Match) -> str:
        original_url = match.group(2)
        info = mapping.get(original_url)
        if not info:
            return match.group(0)  # 未处理的保留原样

        resolved_url = info.get("resolved_url", original_url)
        caption = info.get("caption", "")
        if not caption or caption == "图片解析失败":
            caption = match.group(1) or "图片"

        img_line = f"![{caption}]({resolved_url})"
        desc_line = f"图片描述：{caption}（图片URL：{resolved_url}）"
        return f"{img_line}\n{desc_line}"

    return _IMG_PATTERN.sub(_replace, markdown_text)


# ---------------------------------------------------------------------------
# 5. 元数据构建
# ---------------------------------------------------------------------------

def build_image_metadata(mapping: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """
    从处理映射中构建图片元数据列表。

    Returns:
        [{ "url": ..., "relative_path": ..., "caption": ..., "status": "ok" | "failed" }, ...]
    """
    result = []
    for original_url, info in mapping.items():
        result.append({
            "url": info.get("resolved_url", original_url),
            "relative_path": original_url,
            "caption": info.get("caption", ""),
            "status": info.get("status", "ok"),
        })
    return result


# ---------------------------------------------------------------------------
# 6. 主入口：enrich_markdown
# ---------------------------------------------------------------------------

async def enrich_markdown(
    markdown_text: str,
    assets_map: dict[str, bytes] | None = None,
    doc_id: str = "",
    base_url: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    入队前的 markdown 图片统一处理主函数。

    1. 解析 markdown 中所有图片 URL
    2. 规范化 URL（相对路径落盘 + 生成公开 URL）
    3. 并发调用 VLM caption
    4. 重写 markdown
    5. 返回 (重写后的 markdown, images 元数据列表)

    Args:
        markdown_text: 原始 markdown 文本
        assets_map: ZIP 中提取的资产映射 { 相对路径: bytes }
        doc_id: 文档 ID
        base_url: 后端公开 URL 基础地址

    Returns:
        (enriched_markdown, images_metadata)
    """
    if not markdown_text:
        return markdown_text, []

    assets_map = assets_map or {}

    # 1. 提取所有图片 URL（去重）
    matches = _IMG_PATTERN.findall(markdown_text)
    if not matches:
        return markdown_text, []

    unique_urls = list(dict.fromkeys(url for _, url in matches))

    # 限制处理图片数量
    max_images = llm_settings.VISION_CAPTION_MAX_IMAGES
    if len(unique_urls) > max_images:
        logger.warning(
            "图片数量超限，截断处理",
            total=len(unique_urls),
            max=max_images,
        )
        unique_urls = unique_urls[:max_images]

    # 2. 规范化 URL
    url_mapping: dict[str, dict[str, str]] = {}
    for raw_url in unique_urls:
        resolved = resolve_image_url(raw_url, assets_map, doc_id, base_url)
        if resolved:
            url_mapping[raw_url] = {"resolved_url": resolved, "caption": "", "status": "ok"}
        else:
            url_mapping[raw_url] = {"resolved_url": raw_url, "caption": "图片解析失败", "status": "failed"}

    # 3. 并发 caption（使用 semaphore 控制并发）
    sem = asyncio.Semaphore(llm_settings.VISION_CAPTION_CONCURRENCY)

    async def _caption_with_limit(raw_url: str) -> None:
        info = url_mapping[raw_url]
        if info["status"] == "failed":
            return
        async with sem:
            try:
                caption = await caption_image(info["resolved_url"])
                info["caption"] = caption
            except Exception as e:
                logger.error("caption 失败，降级保留原图", url=raw_url, error=str(e))
                info["caption"] = "图片解析失败"
                info["status"] = "failed"

    await asyncio.gather(*[_caption_with_limit(u) for u in unique_urls])

    # 4. 重写 markdown
    enriched = rewrite_markdown_images(markdown_text, url_mapping)

    # 5. 构建元数据
    images_metadata = build_image_metadata(url_mapping)

    logger.info(
        "图片处理完成",
        doc_id=doc_id,
        total_images=len(unique_urls),
        success=sum(1 for m in images_metadata if m["status"] == "ok"),
        failed=sum(1 for m in images_metadata if m["status"] == "failed"),
    )

    return enriched, images_metadata
