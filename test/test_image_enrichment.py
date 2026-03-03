# -*- coding: utf-8 -*-
"""
图像理解功能测试

覆盖 PLAN.md 中定义的测试场景：
1. ZIP 含 markdown + 图片 → 入队内容含 caption 和描述文本
2. markdown 含绝对 URL 图片 → 直接 caption + 重写
3. 图片 caption 失败 → 文档仍入队，保留原图，描述为占位
4. 无图片 markdown → 内容不变
5. 清洗回归 → 文档 URL 不替换，非文档类型仍替换
6. 路由安全 → assets 路径穿越拒绝
7. 数据模型透传 → images 字段沿 pipeline 传递
"""

from __future__ import annotations

import asyncio
import io
import os
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# ===========================================================================
# 1. markdown_image_enricher 单元测试
# ===========================================================================
from app.api.services.markdown_image_enricher import (
    _IMG_PATTERN,
    _find_asset_key,
    _sanitize_path,
    build_image_metadata,
    extract_markdown_and_assets,
    resolve_image_url,
    rewrite_markdown_images,
    enrich_markdown,
    save_asset_to_disk,
    ASSETS_ROOT,
)


class TestExtractMarkdownAndAssets:
    """Test ZIP extraction."""

    def _make_zip(self, files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        return buf.getvalue()

    def test_basic_extraction(self):
        md = "# Hello\n![img](images/a.png)"
        img_data = b"\x89PNG_FAKE"
        zip_bytes = self._make_zip({
            "doc/index.md": md,
            "doc/images/a.png": img_data,
        })

        text, assets = extract_markdown_and_assets(zip_bytes)
        assert text == md
        assert "doc/images/a.png" in assets
        assert assets["doc/images/a.png"] == img_data

    def test_no_images(self):
        md = "# No images here"
        zip_bytes = self._make_zip({"readme.md": md})
        text, assets = extract_markdown_and_assets(zip_bytes)
        assert text == md
        assert len(assets) == 0

    def test_no_markdown(self):
        zip_bytes = self._make_zip({"data.json": b"{}"})
        text, assets = extract_markdown_and_assets(zip_bytes)
        assert text == ""
        assert len(assets) == 0


class TestImagePattern:
    """Test markdown image regex."""

    def test_basic(self):
        matches = _IMG_PATTERN.findall("![alt](http://img.com/a.png)")
        assert len(matches) == 1
        assert matches[0] == ("alt", "http://img.com/a.png")

    def test_empty_alt(self):
        matches = _IMG_PATTERN.findall("![](images/x.jpg)")
        assert len(matches) == 1
        assert matches[0] == ("", "images/x.jpg")

    def test_multiple(self):
        text = "![a](u1) text ![b](u2)"
        matches = _IMG_PATTERN.findall(text)
        assert len(matches) == 2


class TestSanitizePath:
    """Test path sanitization."""

    def test_dotdot_removed(self):
        result = _sanitize_path("../../etc/passwd")
        assert ".." not in result
        assert result == "etc/passwd"

    def test_normal_path(self):
        result = _sanitize_path("images/fig1.png")
        assert result == "images/fig1.png"


class TestFindAssetKey:
    """Test asset key matching."""

    def test_exact_match(self):
        assets = {"images/a.png": b"data"}
        assert _find_asset_key("images/a.png", assets) == "images/a.png"

    def test_prefix_dot_slash(self):
        assets = {"images/a.png": b"data"}
        assert _find_asset_key("./images/a.png", assets) == "images/a.png"

    def test_suffix_match(self):
        assets = {"doc/images/a.png": b"data"}
        assert _find_asset_key("images/a.png", assets) == "doc/images/a.png"

    def test_no_match(self):
        assets = {"images/a.png": b"data"}
        assert _find_asset_key("other/b.jpg", assets) is None


class TestResolveImageUrl:
    """Test URL resolution."""

    def test_absolute_url_passthrough(self):
        result = resolve_image_url(
            "https://example.com/img.png", {}, "doc1"
        )
        assert result == "https://example.com/img.png"

    def test_relative_url_resolves(self, tmp_path):
        assets = {"images/fig.png": b"\x89PNG"}
        with patch.object(
            Path, "write_bytes"
        ), patch(
            "app.api.services.markdown_image_enricher.ASSETS_ROOT", tmp_path
        ):
            result = resolve_image_url(
                "images/fig.png",
                assets,
                "test-doc",
                base_url="http://localhost:8000",
            )
        assert result is not None
        assert "test-doc" in result
        assert result.startswith("http://localhost:8000/api/v1/knowledge/assets/")

    def test_missing_asset(self):
        result = resolve_image_url("missing.png", {}, "doc1")
        assert result is None


class TestRewriteMarkdownImages:
    """Test markdown rewriting."""

    def test_rewrite_with_caption(self):
        md = "before\n![](http://img.com/a.png)\nafter"
        mapping = {
            "http://img.com/a.png": {
                "resolved_url": "http://img.com/a.png",
                "caption": "一张示意图",
            }
        }
        result = rewrite_markdown_images(md, mapping)
        assert "![一张示意图](http://img.com/a.png)" in result
        assert "图片描述：一张示意图（图片URL：http://img.com/a.png）" in result

    def test_rewrite_preserves_unmatched(self):
        md = "![alt](unknown.png)"
        result = rewrite_markdown_images(md, {})
        assert result == md

    def test_rewrite_failed_caption(self):
        md = "![](http://img.com/a.png)"
        mapping = {
            "http://img.com/a.png": {
                "resolved_url": "http://img.com/a.png",
                "caption": "图片解析失败",
            }
        }
        result = rewrite_markdown_images(md, mapping)
        # 降级使用默认 "图片" alt text
        assert "![图片](http://img.com/a.png)" in result


class TestBuildImageMetadata:
    """Test metadata building."""

    def test_builds_list(self):
        mapping = {
            "img/a.png": {
                "resolved_url": "http://host/a.png",
                "caption": "cap",
                "status": "ok",
            },
            "img/b.png": {
                "resolved_url": "http://host/b.png",
                "caption": "图片解析失败",
                "status": "failed",
            },
        }
        result = build_image_metadata(mapping)
        assert len(result) == 2
        assert result[0]["status"] == "ok"
        assert result[1]["status"] == "failed"


class TestEnrichMarkdown:
    """Test the main enrich_markdown entry point."""

    @pytest.mark.asyncio
    async def test_no_images_passthrough(self):
        md = "# Hello\nSome text without images."
        result, images = await enrich_markdown(md)
        assert result == md
        assert images == []

    @pytest.mark.asyncio
    async def test_empty_markdown(self):
        result, images = await enrich_markdown("")
        assert result == ""
        assert images == []

    @pytest.mark.asyncio
    async def test_with_http_images(self):
        md = "![](https://example.com/photo.jpg)"
        with patch(
            "app.api.services.markdown_image_enricher.caption_image",
            new_callable=AsyncMock,
            return_value="一张照片",
        ):
            result, images = await enrich_markdown(md, doc_id="d1")

        assert "一张照片" in result
        assert len(images) == 1
        assert images[0]["status"] == "ok"
        assert images[0]["caption"] == "一张照片"

    @pytest.mark.asyncio
    async def test_caption_failure_degrades(self):
        md = "![](https://example.com/broken.jpg)"
        with patch(
            "app.api.services.markdown_image_enricher.caption_image",
            new_callable=AsyncMock,
            side_effect=Exception("VLM down"),
        ):
            result, images = await enrich_markdown(md, doc_id="d2")

        # 应降级保留原图
        assert "broken.jpg" in result
        assert len(images) == 1
        assert images[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_zip_with_relative_images(self):
        """Test Case 1 from PLAN: ZIP 含 markdown + 图片"""
        md = "# Doc\n![](images/chart.png)\nsome text"
        assets = {"images/chart.png": b"\x89PNG_FAKE"}

        with patch(
            "app.api.services.markdown_image_enricher.caption_image",
            new_callable=AsyncMock,
            return_value="柱状图",
        ), patch(
            "app.api.services.markdown_image_enricher.save_asset_to_disk",
            return_value=Path("/tmp/fake"),
        ):
            result, images = await enrich_markdown(
                md, assets_map=assets, doc_id="zip-doc-1",
                base_url="http://localhost:8000",
            )

        assert "柱状图" in result
        assert "图片描述" in result
        assert len(images) == 1
        assert images[0]["status"] == "ok"


# ===========================================================================
# 2. cleaning 回归测试 (Test Case 5)
# ===========================================================================
from app.pipeline.feature_pipeline.utils.cleaning import clean_text


class TestCleanTextPreserveUrls:
    """Test that preserve_urls=True keeps URLs intact."""

    def test_default_replaces_urls(self):
        text = "Visit https://example.com for more info"
        result = clean_text(text)
        assert "[URL]" in result
        assert "https://example.com" not in result

    def test_preserve_urls_keeps_them(self):
        text = "Visit https://example.com for more info"
        result = clean_text(text, preserve_urls=True)
        assert "https://example.com" in result
        assert "[URL]" not in result

    def test_none_input(self):
        assert clean_text(None) == ""


# ===========================================================================
# 3. 数据模型透传测试 (Test Case 7 - data model)
# ===========================================================================
from app.pipeline.feature_pipeline.models.raw import DocumentRawModel
from app.pipeline.feature_pipeline.models.clean import DocumentCleanedModel
from app.pipeline.feature_pipeline.models.chunk import DocumentChunkModel


class TestDataModelImagesField:
    """Test that images field is properly carried through models."""

    _sample_images = [
        {"url": "http://host/img.png", "relative_path": "img.png", "caption": "test", "status": "ok"}
    ]

    def test_raw_model_images(self):
        m = DocumentRawModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md", content="hello",
            images=self._sample_images,
        )
        assert m.images == self._sample_images

    def test_raw_model_no_images(self):
        m = DocumentRawModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md", content="hello",
        )
        assert m.images is None

    def test_clean_model_images(self):
        m = DocumentCleanedModel(
            entry_id="1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md", cleaned_content="hello",
            images=self._sample_images,
        )
        _, payload = m.to_payload()
        assert payload["images"] == self._sample_images

    def test_chunk_model_images(self):
        m = DocumentChunkModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", filename="test.md",
            path="test.md", chunk_id="c1", chunk_content="hello",
            images=self._sample_images,
        )
        assert m.images == self._sample_images


class TestDocumentRawModelSerialization:
    """Test that images round-trips through JSON serialization."""

    def test_serialize_deserialize(self):
        images = [
            {"url": "http://host/img.png", "relative_path": "img.png", "caption": "cap", "status": "ok"}
        ]
        m = DocumentRawModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md", content="hello", images=images,
        )
        json_str = m.model_dump_json()
        restored = DocumentRawModel.model_validate_json(json_str)
        assert restored.images == images


# ===========================================================================
# 4. 清洗 handler 透传 images (cleaning_data_handlers)
# ===========================================================================
from app.pipeline.feature_pipeline.data_logic.cleaning_data_handlers import DocumentCleaningHandler


class TestDocumentCleaningHandlerImages:
    """Test that DocumentCleaningHandler passes images through."""

    def test_images_passed_through(self):
        images = [{"url": "http://host/a.png", "caption": "test", "status": "ok", "relative_path": "a.png"}]
        raw = DocumentRawModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md", content="![cap](http://host/a.png)\n图片描述：cap",
            images=images,
        )
        handler = DocumentCleaningHandler()
        cleaned = handler.clean(raw)
        assert cleaned.images == images

    def test_preserves_urls_in_content(self):
        raw = DocumentRawModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md",
            content="![cap](http://host/a.png)\nSee https://example.com",
        )
        handler = DocumentCleaningHandler()
        cleaned = handler.clean(raw)
        assert "http://host/a.png" in cleaned.cleaned_content
        assert "https://example.com" in cleaned.cleaned_content
        assert "[URL]" not in cleaned.cleaned_content


# ===========================================================================
# 5. 分块 handler 透传 images (chunking_data_handlers)
# ===========================================================================
from app.pipeline.feature_pipeline.data_logic.chunking_data_handlers import DocumentChunkingHandler


class TestDocumentChunkingHandlerImages:
    """Test that DocumentChunkingHandler passes images to chunks."""

    def test_images_in_chunks(self):
        images = [{"url": "http://host/a.png", "caption": "test", "status": "ok", "relative_path": "a.png"}]
        cleaned = DocumentCleanedModel(
            entry_id="1", type="documents",
            knowledge_id="kb1", doc_id="d1", path="test.md",
            filename="test.md", cleaned_content="Short text",
            images=images,
        )
        handler = DocumentChunkingHandler()
        chunks = handler.chunk(cleaned)
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.images == images


# ===========================================================================
# 6. 嵌入 handler 透传 images (embedding_data_handlers)
# ===========================================================================
from app.pipeline.feature_pipeline.data_logic.embedding_data_handlers import DocumentEmbeddingHandler


class TestDocumentEmbeddingHandlerImages:
    """Test that DocumentEmbeddingHandler passes images to embedded model."""

    def test_images_in_embedded(self):
        import numpy as np
        images = [{"url": "http://host/a.png", "caption": "test", "status": "ok", "relative_path": "a.png"}]
        chunk = DocumentChunkModel(
            entry_id="e1", type="documents",
            knowledge_id="kb1", doc_id="d1", filename="test.md",
            path="test.md", chunk_id="c1", chunk_content="hello world",
            images=images,
        )
        with patch(
            "app.pipeline.feature_pipeline.data_logic.embedding_data_handlers.embedd_text",
            return_value=np.zeros(1024),
        ):
            handler = DocumentEmbeddingHandler()
            embedded = handler.embedd(chunk)
        assert embedded.images == images
        _, _, payload = embedded.to_payload()
        assert payload["images"] == images


# ===========================================================================
# 7. 路由安全测试 (Test Case 7 - security)
# ===========================================================================
import pytest

try:
    from httpx import ASGITransport, AsyncClient
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


@pytest.mark.skipif(not _HAS_HTTPX, reason="httpx not available")
class TestAssetRouterSecurity:
    """Test static asset route security controls."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create test client with patched assets root."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # Create a test file
        doc_dir = tmp_path / "test-doc"
        doc_dir.mkdir()
        test_img = doc_dir / "img.png"
        test_img.write_bytes(b"\x89PNG_FAKE")

        resolved_tmp = tmp_path.resolve()

        patcher = patch("app.api.v1.knowledge_v1._ASSETS_ROOT", resolved_tmp)
        patcher.start()

        from app.api.v1 import knowledge_v1
        app = FastAPI()
        # Router already has prefix="/knowledge"
        app.include_router(knowledge_v1.router)

        yield TestClient(app)

        patcher.stop()

    def test_valid_asset(self, client):
        resp = client.get("/knowledge/assets/test-doc/img.png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_path_traversal_rejected(self, client):
        resp = client.get("/knowledge/assets/test-doc/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)

    def test_nonexistent_file(self, client):
        resp = client.get("/knowledge/assets/test-doc/missing.png")
        assert resp.status_code == 404

    def test_absolute_path_rejected(self, client):
        resp = client.get("/knowledge/assets/test-doc//etc/passwd")
        # FastAPI normalizes double slashes, but our check catches absolute paths
        assert resp.status_code in (400, 404)


# ===========================================================================
# 8. _publish_to_queue with images
# ===========================================================================
class TestPublishToQueueImages:
    """Test that _publish_to_queue includes images field."""

    def test_publish_with_images(self):
        from app.api.services.document import _publish_to_queue
        images = [{"url": "http://host/a.png", "caption": "test", "status": "ok", "relative_path": "a.png"}]

        with patch("app.api.services.document.publish_to_rabbitmq") as mock_publish:
            _publish_to_queue("col1", "test.md", "content", "doc1", images)

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        import json
        data = json.loads(call_args.kwargs.get("data") or call_args[1].get("data") or call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs["data"])
        assert data["images"] == images

    def test_publish_without_images(self):
        from app.api.services.document import _publish_to_queue

        with patch("app.api.services.document.publish_to_rabbitmq") as mock_publish:
            _publish_to_queue("col1", "test.md", "content", "doc1")

        mock_publish.assert_called_once()


# ===========================================================================
# 9. Integration: enrich_markdown full pipeline
# ===========================================================================
class TestEnrichMarkdownIntegration:
    """Integration-style tests for the full enrichment pipeline."""

    @pytest.mark.asyncio
    async def test_multiple_images_mixed(self):
        """Some relative, some absolute URLs."""
        md = (
            "# Report\n"
            "![](images/chart.png)\n"
            "![](https://cdn.example.com/photo.jpg)\n"
            "![](images/diagram.png)\n"
        )
        assets = {
            "images/chart.png": b"CHART",
            "images/diagram.png": b"DIAGRAM",
        }

        async def mock_caption(url):
            if "chart" in url:
                return "柱状图"
            elif "photo" in url:
                return "照片"
            elif "diagram" in url:
                return "流程图"
            return "图片"

        with patch(
            "app.api.services.markdown_image_enricher.caption_image",
            side_effect=mock_caption,
        ), patch(
            "app.api.services.markdown_image_enricher.save_asset_to_disk",
            return_value=Path("/tmp/fake"),
        ):
            result, images = await enrich_markdown(
                md, assets_map=assets, doc_id="int-1",
                base_url="http://localhost:8000",
            )

        assert "柱状图" in result
        assert "照片" in result
        assert "流程图" in result
        assert len(images) == 3
        assert all(img["status"] == "ok" for img in images)

    @pytest.mark.asyncio
    async def test_max_images_limit(self):
        """Test that images beyond the limit are ignored."""
        lines = [f"![](https://img.com/{i}.png)" for i in range(30)]
        md = "\n".join(lines)

        call_count = 0

        async def mock_caption(url):
            nonlocal call_count
            call_count += 1
            return f"cap-{call_count}"

        with patch(
            "app.api.services.markdown_image_enricher.caption_image",
            side_effect=mock_caption,
        ), patch(
            "app.api.services.markdown_image_enricher.llm_settings"
        ) as mock_settings:
            mock_settings.VISION_CAPTION_MAX_IMAGES = 5
            mock_settings.VISION_CAPTION_CONCURRENCY = 2
            mock_settings.SILICON_KEY = "test"
            mock_settings.SILICON_BASE_URL = "http://test"
            mock_settings.PUBLIC_BACKEND_BASE_URL = "http://localhost:8000"
            result, images = await enrich_markdown(md, doc_id="limit-test")

        assert len(images) == 5
        assert call_count == 5
