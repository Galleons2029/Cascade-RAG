# -*- coding: utf-8 -*-
# @Time   : 2026/1/14
# @Author : Galleons
# @File   : kb_manager_v1.py

"""
知识库管理 Agent API 端点
提供基于自然语言的知识库管理功能
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.agent.graph.kb_manager import (
    arun_kb_manager,
    list_collections,
    get_collection_info,
    create_collection,
    delete_collection,
    add_documents,
    update_document,
    smart_upsert_document,
    check_document_exists,
    search_documents,
    delete_documents,
    scroll_documents,
    update_collection_alias,
)

router = APIRouter()


# ============ 请求/响应模型 ============

class AgentChatRequest(BaseModel):
    """Agent 对话请求"""
    message: str = Field(..., description="用户的自然语言指令", examples=["列出所有知识库"])
    user_id: str = Field(default="default", description="用户ID")


class AgentChatResponse(BaseModel):
    """Agent 对话响应"""
    response: str = Field(..., description="Agent 的回复")
    success: bool = Field(default=True)


class CollectionCreateRequest(BaseModel):
    """创建集合请求"""
    collection_name: str = Field(..., description="集合名称")
    vector_size: int = Field(default=1024, description="向量维度")
    distance: str = Field(default="cosine", description="距离度量: cosine, euclid, dot")


class CollectionResponse(BaseModel):
    """集合响应"""
    message: str
    success: bool = True


class DocumentAddRequest(BaseModel):
    """添加文档请求"""
    collection_name: str = Field(..., description="集合名称")
    texts: list[str] = Field(..., description="文档文本列表")
    metadata: Optional[list[dict]] = Field(default=None, description="元数据列表")


class DocumentSearchRequest(BaseModel):
    """搜索文档请求"""
    collection_name: str = Field(..., description="集合名称")
    query: str = Field(..., description="搜索查询")
    limit: int = Field(default=5, ge=1, le=100, description="返回数量")


class DocumentDeleteRequest(BaseModel):
    """删除文档请求"""
    collection_name: str = Field(..., description="集合名称")
    point_ids: Optional[list[str]] = Field(default=None, description="文档ID列表")
    filter_field: Optional[str] = Field(default=None, description="过滤字段")
    filter_value: Optional[str] = Field(default=None, description="过滤值")


class AliasRequest(BaseModel):
    """别名管理请求"""
    collection_name: str = Field(..., description="集合名称")
    alias_name: str = Field(..., description="别名名称")
    action: str = Field(default="create", description="操作: create, delete")


class DocumentUpdateRequest(BaseModel):
    """更新文档请求"""
    collection_name: str = Field(..., description="集合名称")
    document_id: str = Field(..., description="文档ID")
    new_text: str = Field(..., description="新的文档内容")
    metadata: Optional[dict] = Field(default=None, description="新的元数据")


class SmartUpsertRequest(BaseModel):
    """智能添加/更新文档请求"""
    collection_name: str = Field(..., description="集合名称")
    text: str = Field(..., description="文档内容")
    similarity_threshold: float = Field(default=0.85, ge=0, le=1, description="相似度阈值")
    metadata: Optional[dict] = Field(default=None, description="元数据")


class CheckDocumentRequest(BaseModel):
    """检查文档存在性请求"""
    collection_name: str = Field(..., description="集合名称")
    text: str = Field(..., description="要检查的文档内容")
    similarity_threshold: float = Field(default=0.85, ge=0, le=1, description="相似度阈值")


# ============ Agent 对话接口 ============

@router.post("/chat", response_model=AgentChatResponse, summary="知识库管理对话")
async def kb_manager_chat(request: AgentChatRequest) -> AgentChatResponse:
    """
    使用自然语言与知识库管理 Agent 交互。
    
    支持的操作示例:
    - "列出所有知识库集合"
    - "创建一个名为 my_kb 的知识库"
    - "查看 my_kb 的详细信息"
    - "在 my_kb 中搜索 '人工智能'"
    - "删除 my_kb 知识库"
    """
    try:
        response = await arun_kb_manager(request.message, request.user_id)
        return AgentChatResponse(response=response, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 集合管理接口 ============

@router.get("/collections", response_model=CollectionResponse, summary="列出所有集合")
async def api_list_collections() -> CollectionResponse:
    """获取 Qdrant 中所有知识库集合列表"""
    try:
        result = list_collections.invoke({})
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_name}", response_model=CollectionResponse, summary="获取集合详情")
async def api_get_collection(collection_name: str) -> CollectionResponse:
    """获取指定集合的详细信息"""
    try:
        result = get_collection_info.invoke({"collection_name": collection_name})
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections", response_model=CollectionResponse, summary="创建集合")
async def api_create_collection(request: CollectionCreateRequest) -> CollectionResponse:
    """创建新的知识库集合"""
    try:
        result = create_collection.invoke({
            "collection_name": request.collection_name,
            "vector_size": request.vector_size,
            "distance": request.distance,
        })
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{collection_name}", response_model=CollectionResponse, summary="删除集合")
async def api_delete_collection(collection_name: str) -> CollectionResponse:
    """删除指定的知识库集合（危险操作）"""
    try:
        result = delete_collection.invoke({"collection_name": collection_name})
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 文档管理接口 ============

@router.post("/documents", response_model=CollectionResponse, summary="添加文档")
async def api_add_documents(request: DocumentAddRequest) -> CollectionResponse:
    """向知识库集合中添加文档（不检查重复）"""
    try:
        params = {
            "collection_name": request.collection_name,
            "texts": request.texts,
        }
        if request.metadata:
            params["metadata"] = request.metadata
        result = add_documents.invoke(params)
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/documents", response_model=CollectionResponse, summary="更新文档")
async def api_update_document(request: DocumentUpdateRequest) -> CollectionResponse:
    """更新指定ID的文档"""
    try:
        params = {
            "collection_name": request.collection_name,
            "document_id": request.document_id,
            "new_text": request.new_text,
        }
        if request.metadata:
            params["metadata"] = request.metadata
        result = update_document.invoke(params)
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/smart-upsert", response_model=CollectionResponse, summary="智能添加/更新")
async def api_smart_upsert(request: SmartUpsertRequest) -> CollectionResponse:
    """
    智能添加或更新文档。
    
    自动检查是否存在相似文档：
    - 如果存在相似度超过阈值的文档，则更新该文档
    - 如果不存在，则添加为新文档
    """
    try:
        params = {
            "collection_name": request.collection_name,
            "text": request.text,
            "similarity_threshold": request.similarity_threshold,
        }
        if request.metadata:
            params["metadata"] = request.metadata
        result = smart_upsert_document.invoke(params)
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/check-exists", response_model=CollectionResponse, summary="检查文档存在性")
async def api_check_document_exists(request: CheckDocumentRequest) -> CollectionResponse:
    """检查知识库中是否已存在相似的文档"""
    try:
        result = check_document_exists.invoke({
            "collection_name": request.collection_name,
            "text": request.text,
            "similarity_threshold": request.similarity_threshold,
        })
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/search", response_model=CollectionResponse, summary="搜索文档")
async def api_search_documents(request: DocumentSearchRequest) -> CollectionResponse:
    """在知识库集合中搜索相关文档"""
    try:
        result = search_documents.invoke({
            "collection_name": request.collection_name,
            "query": request.query,
            "limit": request.limit,
        })
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents", response_model=CollectionResponse, summary="删除文档")
async def api_delete_documents(request: DocumentDeleteRequest) -> CollectionResponse:
    """从知识库集合中删除文档"""
    try:
        params = {"collection_name": request.collection_name}
        if request.point_ids:
            params["point_ids"] = request.point_ids
        if request.filter_field and request.filter_value:
            params["filter_field"] = request.filter_field
            params["filter_value"] = request.filter_value
        result = delete_documents.invoke(params)
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{collection_name}", response_model=CollectionResponse, summary="浏览文档")
async def api_scroll_documents(
    collection_name: str,
    limit: int = 10,
    offset: Optional[str] = None
) -> CollectionResponse:
    """分页浏览知识库集合中的文档"""
    try:
        params = {
            "collection_name": collection_name,
            "limit": limit,
        }
        if offset:
            params["offset"] = offset
        result = scroll_documents.invoke(params)
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 别名管理接口 ============

@router.post("/aliases", response_model=CollectionResponse, summary="管理别名")
async def api_manage_alias(request: AliasRequest) -> CollectionResponse:
    """创建或删除集合别名"""
    try:
        result = update_collection_alias.invoke({
            "collection_name": request.collection_name,
            "alias_name": request.alias_name,
            "action": request.action,
        })
        return CollectionResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
