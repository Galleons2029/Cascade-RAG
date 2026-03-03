# -*- coding: utf-8 -*-
# @Time   : 2026/1/14
# @Author : Galleons
# @File   : kb_manager.py

"""
知识库管理 Agent - 基于 LangGraph 实现对 Qdrant 向量数据库集合的增删改查操作
"""

import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.configs import llm_config, qdrant_config
from app.core.rag.embedding import embedd_text_tolist
import app.core.logger_utils as logger_utils


logger = logger_utils.get_logger(__name__)


# ============ Qdrant 客户端初始化 ============
def get_qdrant_client() -> QdrantClient:
    """获取 Qdrant 客户端连接"""
    return QdrantClient(
        host=qdrant_config.QDRANT_DATABASE_HOST or "localhost",
        port=qdrant_config.QDRANT_DATABASE_PORT or 6333,
    )


# ============ 定义工具函数 ============

@tool
def list_collections() -> str:
    """
    列出 Qdrant 中所有的知识库集合。
    返回所有集合的名称列表及其基本信息。
    """
    try:
        client = get_qdrant_client()
        collections = client.get_collections()
        
        if not collections.collections:
            return "当前没有任何知识库集合。"
        
        result = "📚 **知识库集合列表:**\n\n"
        for i, collection in enumerate(collections.collections, 1):
            collection_info = client.get_collection(collection.name)
            result += f"{i}. **{collection.name}**\n"
            result += f"   - 向量数量: {collection_info.points_count}\n"
            vectors = collection_info.config.params.vectors
            vector_size = vectors.size if hasattr(vectors, 'size') else 'N/A'
            result += f"   - 向量维度: {vector_size}\n"
            result += f"   - 状态: {collection_info.status}\n\n"
        
        return result
    except Exception as e:
        logger.error(f"列出集合失败: {e}")
        return f"❌ 列出集合失败: {str(e)}"


@tool
def get_collection_info(collection_name: str) -> str:
    """
    获取指定知识库集合的详细信息。
    
    Args:
        collection_name: 要查询的集合名称
    """
    try:
        client = get_qdrant_client()
        collection_info = client.get_collection(collection_name)
        
        result = f"📖 **集合详情: {collection_name}**\n\n"
        result += f"- **向量数量**: {collection_info.points_count}\n"
        result += f"- **索引向量数量**: {collection_info.indexed_vectors_count}\n"
        result += f"- **状态**: {collection_info.status}\n"
        
        # 向量配置
        vectors_config = collection_info.config.params.vectors
        if hasattr(vectors_config, 'size'):
            result += f"- **向量维度**: {vectors_config.size}\n"
            result += f"- **距离度量**: {vectors_config.distance}\n"
        
        # 优化器配置
        optimizer = collection_info.config.optimizer_config
        result += f"- **删除阈值**: {optimizer.deleted_threshold}\n"
        result += f"- **索引阈值**: {optimizer.indexing_threshold}\n"
        
        return result
    except Exception as e:
        logger.error(f"获取集合信息失败: {e}")
        return f"❌ 获取集合 '{collection_name}' 信息失败: {str(e)}"


@tool
def create_collection(
    collection_name: str,
    vector_size: int = 1024,
    distance: str = "cosine"
) -> str:
    """
    创建新的知识库集合。
    
    Args:
        collection_name: 新集合的名称
        vector_size: 向量维度，默认1024（适用于bge-m3模型）
        distance: 距离度量方式，可选 'cosine', 'euclid', 'dot'，默认 'cosine'
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否已存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name in existing_collections:
            return f"⚠️ 集合 '{collection_name}' 已存在，无需重复创建。"
        
        # 映射距离度量
        distance_map = {
            "cosine": Distance.COSINE,
            "euclid": Distance.EUCLID,
            "dot": Distance.DOT,
        }
        dist = distance_map.get(distance.lower(), Distance.COSINE)
        
        # 创建集合
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=dist),
            # 可选：启用量化以节省内存
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                ),
            ),
        )
        
        return f"✅ 成功创建知识库集合 '{collection_name}'！\n- 向量维度: {vector_size}\n- 距离度量: {distance}"
    except Exception as e:
        logger.error(f"创建集合失败: {e}")
        return f"❌ 创建集合 '{collection_name}' 失败: {str(e)}"


@tool
def delete_collection(collection_name: str) -> str:
    """
    删除指定的知识库集合。警告：此操作不可恢复！
    
    Args:
        collection_name: 要删除的集合名称
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"⚠️ 集合 '{collection_name}' 不存在。"
        
        # 获取集合信息用于日志
        collection_info = client.get_collection(collection_name)
        points_count = collection_info.points_count
        
        # 删除集合
        client.delete_collection(collection_name=collection_name)
        
        return f"✅ 成功删除知识库集合 '{collection_name}'！\n- 已删除 {points_count} 条向量数据"
    except Exception as e:
        logger.error(f"删除集合失败: {e}")
        return f"❌ 删除集合 '{collection_name}' 失败: {str(e)}"


@tool
def add_documents(
    collection_name: str,
    texts: list[str],
    metadata: list[dict] | None = None
) -> str:
    """
    向知识库集合中添加文档。会自动进行向量化处理。
    
    Args:
        collection_name: 目标集合名称
        texts: 要添加的文本列表
        metadata: 可选的元数据列表，与 texts 一一对应
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。请先创建集合。"
        
        if not texts:
            return "❌ 文本列表不能为空。"
        
        # 准备元数据
        if metadata is None:
            metadata = [{}] * len(texts)
        elif len(metadata) != len(texts):
            return "❌ 元数据数量必须与文本数量相同。"
        
        # 生成向量并构建 points
        points = []
        for i, (text, meta) in enumerate(zip(texts, metadata)):
            # 生成向量
            vector = embedd_text_tolist(text)
            
            # 构建 payload
            payload = {
                "content": text,
                **meta
            }
            
            # 创建 point
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=payload
            )
            points.append(point)
        
        # 批量插入
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        
        return f"✅ 成功向集合 '{collection_name}' 添加 {len(texts)} 条文档！"
    except Exception as e:
        logger.error(f"添加文档失败: {e}")
        return f"❌ 添加文档失败: {str(e)}"


@tool
def search_documents(
    collection_name: str,
    query: str,
    limit: int = 5,
    score_threshold: float = 0.0
) -> str:
    """
    在知识库集合中搜索相关文档。返回文档ID、相似度和内容。
    
    Args:
        collection_name: 目标集合名称
        query: 搜索查询文本
        limit: 返回结果数量，默认5条
        score_threshold: 相似度阈值，只返回高于此阈值的结果，默认0.0
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。"
        
        # 生成查询向量
        query_vector = embedd_text_tolist(query)
        
        # 执行搜索
        results = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit
        ).points
        
        # 过滤低于阈值的结果
        results = [r for r in results if r.score >= score_threshold]
        
        if not results:
            return f"在集合 '{collection_name}' 中未找到相关文档（相似度阈值: {score_threshold}）。"
        
        result_str = f"🔍 **搜索结果 (集合: {collection_name})**\n\n"
        result_str += f"查询: \"{query}\"\n"
        result_str += f"共找到 {len(results)} 条相关文档:\n\n"
        
        for i, hit in enumerate(results, 1):
            content = hit.payload.get("content", "N/A")
            score = hit.score
            doc_id = hit.id
            # 截断长文本
            if len(content) > 200:
                content = content[:200] + "..."
            result_str += f"**{i}. ID: `{doc_id}` | 相似度: {score:.4f}**\n"
            result_str += f"内容: {content}\n\n"
        
        return result_str
    except Exception as e:
        logger.error(f"搜索文档失败: {e}")
        return f"❌ 搜索失败: {str(e)}"


@tool
def update_document(
    collection_name: str,
    document_id: str,
    new_text: str,
    metadata: dict | None = None
) -> str:
    """
    更新知识库中的指定文档。会重新生成向量。
    
    Args:
        collection_name: 目标集合名称
        document_id: 要更新的文档ID
        new_text: 新的文档内容
        metadata: 可选的新元数据，如果不提供则保留原有元数据
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。"
        
        # 获取原有文档信息
        try:
            existing_points = client.retrieve(
                collection_name=collection_name,
                ids=[document_id],
                with_payload=True
            )
            if not existing_points:
                return f"❌ 文档 ID '{document_id}' 不存在。"
            
            old_payload = existing_points[0].payload
        except Exception:
            return f"❌ 文档 ID '{document_id}' 不存在或无法访问。"
        
        # 生成新向量
        new_vector = embedd_text_tolist(new_text)
        
        # 构建新 payload
        new_payload = {
            "content": new_text,
            **(metadata if metadata else {k: v for k, v in old_payload.items() if k != "content"})
        }
        
        # 更新文档
        client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=document_id,
                    vector=new_vector,
                    payload=new_payload
                )
            ]
        )
        
        return f"✅ 成功更新文档 '{document_id}'！"
    except Exception as e:
        logger.error(f"更新文档失败: {e}")
        return f"❌ 更新文档失败: {str(e)}"


@tool
def smart_upsert_document(
    collection_name: str,
    text: str,
    similarity_threshold: float = 0.85,
    metadata: dict | None = None
) -> str:
    """
    智能添加或更新文档。先搜索是否存在高度相似的文档：
    - 如果存在相似度超过阈值的文档，则更新该文档
    - 如果不存在，则添加为新文档
    
    Args:
        collection_name: 目标集合名称
        text: 文档内容
        similarity_threshold: 相似度阈值（0-1），超过此阈值视为相同文档，默认0.85
        metadata: 可选的元数据
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。请先创建集合。"
        
        # 生成向量
        text_vector = embedd_text_tolist(text)
        
        # 搜索相似文档
        results = client.query_points(
            collection_name=collection_name,
            query=text_vector,
            limit=1
        ).points
        
        # 检查是否有高度相似的文档
        if results and results[0].score >= similarity_threshold:
            existing_doc = results[0]
            existing_id = existing_doc.id
            existing_score = existing_doc.score
            existing_content = existing_doc.payload.get("content", "")[:100]
            
            # 更新现有文档
            new_payload = {
                "content": text,
                **(metadata if metadata else {})
            }
            
            client.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(
                        id=existing_id,
                        vector=text_vector,
                        payload=new_payload
                    )
                ]
            )
            
            return (
                f"🔄 **文档已更新**\n\n"
                f"发现相似文档（相似度: {existing_score:.4f}），已进行更新：\n"
                f"- 文档ID: `{existing_id}`\n"
                f"- 原内容预览: {existing_content}...\n"
                f"- 已更新为新内容"
            )
        else:
            # 添加新文档
            new_id = str(uuid.uuid4())
            new_payload = {
                "content": text,
                **(metadata if metadata else {})
            }
            
            client.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(
                        id=new_id,
                        vector=text_vector,
                        payload=new_payload
                    )
                ]
            )
            
            if results:
                most_similar = results[0].score
                return (
                    f"➕ **新文档已添加**\n\n"
                    f"未找到高度相似文档（最高相似度: {most_similar:.4f} < 阈值 {similarity_threshold}），"
                    f"已添加为新文档：\n"
                    f"- 新文档ID: `{new_id}`"
                )
            else:
                return (
                    f"➕ **新文档已添加**\n\n"
                    f"集合为空或未找到相似文档，已添加为新文档：\n"
                    f"- 新文档ID: `{new_id}`"
                )
    except Exception as e:
        logger.error(f"智能添加/更新文档失败: {e}")
        return f"❌ 智能添加/更新文档失败: {str(e)}"


@tool
def check_document_exists(
    collection_name: str,
    text: str,
    similarity_threshold: float = 0.85
) -> str:
    """
    检查知识库中是否已存在相似的文档。
    
    Args:
        collection_name: 目标集合名称
        text: 要检查的文档内容
        similarity_threshold: 相似度阈值（0-1），默认0.85
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。"
        
        # 生成向量
        text_vector = embedd_text_tolist(text)
        
        # 搜索相似文档
        results = client.query_points(
            collection_name=collection_name,
            query=text_vector,
            limit=3
        ).points
        
        if not results:
            return f"✅ 集合 '{collection_name}' 中没有相似文档，可以添加新文档。"
        
        # 检查是否有高度相似的文档
        similar_docs = [r for r in results if r.score >= similarity_threshold]
        
        if similar_docs:
            result_str = f"⚠️ **发现 {len(similar_docs)} 个相似文档**\n\n"
            result_str += f"相似度阈值: {similarity_threshold}\n\n"
            for i, doc in enumerate(similar_docs, 1):
                content = doc.payload.get("content", "N/A")
                if len(content) > 150:
                    content = content[:150] + "..."
                result_str += f"**{i}. ID: `{doc.id}` | 相似度: {doc.score:.4f}**\n"
                result_str += f"内容: {content}\n\n"
            result_str += "建议: 考虑更新现有文档而不是添加重复内容。"
            return result_str
        else:
            result_str = f"✅ **未找到高度相似文档**\n\n"
            result_str += f"最相似文档的相似度为 {results[0].score:.4f}，低于阈值 {similarity_threshold}\n"
            result_str += "可以安全添加新文档。"
            return result_str
    except Exception as e:
        logger.error(f"检查文档存在性失败: {e}")
        return f"❌ 检查失败: {str(e)}"


@tool
def delete_documents(
    collection_name: str,
    point_ids: list[str] | None = None,
    filter_field: str | None = None,
    filter_value: str | None = None
) -> str:
    """
    从知识库集合中删除文档。可以通过ID或过滤条件删除。
    
    Args:
        collection_name: 目标集合名称
        point_ids: 要删除的文档ID列表
        filter_field: 过滤字段名（与 filter_value 配合使用）
        filter_value: 过滤字段值
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。"
        
        if point_ids:
            # 通过ID删除
            client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=point_ids)
            )
            return f"✅ 成功从集合 '{collection_name}' 删除 {len(point_ids)} 条文档！"
        
        elif filter_field and filter_value:
            # 通过过滤条件删除
            client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key=filter_field,
                                match=models.MatchValue(value=filter_value)
                            )
                        ]
                    )
                )
            )
            return f"✅ 成功从集合 '{collection_name}' 删除符合条件 ({filter_field}={filter_value}) 的文档！"
        
        else:
            return "❌ 请提供 point_ids 或者 filter_field 和 filter_value 参数。"
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        return f"❌ 删除文档失败: {str(e)}"


@tool
def scroll_documents(
    collection_name: str,
    limit: int = 10,
    offset: str | None = None
) -> str:
    """
    浏览知识库集合中的文档列表（分页浏览）。
    
    Args:
        collection_name: 目标集合名称
        limit: 每页返回的文档数量，默认10条
        offset: 分页偏移量（用于获取下一页）
    """
    try:
        client = get_qdrant_client()
        
        # 检查集合是否存在
        existing_collections = [c.name for c in client.get_collections().collections]
        if collection_name not in existing_collections:
            return f"❌ 集合 '{collection_name}' 不存在。"
        
        # 滚动查询
        records, next_offset = client.scroll(
            collection_name=collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        
        if not records:
            return f"集合 '{collection_name}' 中没有文档。"
        
        result_str = f"📄 **文档列表 (集合: {collection_name})**\n\n"
        result_str += f"当前显示 {len(records)} 条文档:\n\n"
        
        for i, record in enumerate(records, 1):
            content = record.payload.get("content", "N/A")
            # 截断长文本
            if len(content) > 150:
                content = content[:150] + "..."
            result_str += f"**{i}. ID: {record.id}**\n"
            result_str += f"内容: {content}\n\n"
        
        if next_offset:
            result_str += f"\n---\n💡 还有更多文档，下一页偏移量: `{next_offset}`"
        
        return result_str
    except Exception as e:
        logger.error(f"浏览文档失败: {e}")
        return f"❌ 浏览文档失败: {str(e)}"


@tool
def update_collection_alias(
    collection_name: str,
    alias_name: str,
    action: str = "create"
) -> str:
    """
    管理集合别名。可以创建或删除别名。
    
    Args:
        collection_name: 集合名称
        alias_name: 别名名称
        action: 操作类型，'create' 创建别名，'delete' 删除别名
    """
    try:
        client = get_qdrant_client()
        
        if action.lower() == "create":
            client.update_collection_aliases(
                change_aliases_operations=[
                    models.CreateAliasOperation(
                        create_alias=models.CreateAlias(
                            collection_name=collection_name,
                            alias_name=alias_name
                        )
                    )
                ]
            )
            return f"✅ 成功为集合 '{collection_name}' 创建别名 '{alias_name}'！"
        
        elif action.lower() == "delete":
            client.update_collection_aliases(
                change_aliases_operations=[
                    models.DeleteAliasOperation(
                        delete_alias=models.DeleteAlias(alias_name=alias_name)
                    )
                ]
            )
            return f"✅ 成功删除别名 '{alias_name}'！"
        
        else:
            return "❌ action 参数必须是 'create' 或 'delete'。"
    except Exception as e:
        logger.error(f"管理别名失败: {e}")
        return f"❌ 管理别名失败: {str(e)}"


# ============ 定义所有工具 ============
tools = [
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
]


# ============ 定义 Agent 状态 ============
class KBManagerState(TypedDict):
    """知识库管理 Agent 的状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str


# ============ 初始化 LLM ============
def get_llm():
    """获取 LLM 模型"""
    return init_chat_model(
        model=llm_config.LLM_MODEL_PRO,
        base_url=llm_config.SILICON_BASE_URL,
        api_key=llm_config.SILICON_KEY,
        model_provider="openai",
        temperature=0,
    )


# ============ 定义 Agent 节点 ============
SYSTEM_PROMPT = """你是一个专业的知识库管理助手，负责帮助用户管理 Qdrant 向量数据库中的知识库集合。

你可以执行以下操作：
1. **查看集合**: 列出所有集合、查看集合详情
2. **创建集合**: 创建新的知识库集合
3. **删除集合**: 删除指定的集合（危险操作，需谨慎）
4. **添加文档**: 向集合中添加新文档
5. **更新文档**: 更新已有文档内容
6. **智能添加/更新**: 自动判断文档是否存在，存在则更新，不存在则添加
7. **检查文档**: 检查文档是否已存在于知识库中
8. **搜索文档**: 在集合中搜索相关文档
9. **删除文档**: 从集合中删除文档
10. **浏览文档**: 分页浏览集合中的文档
11. **管理别名**: 为集合创建或删除别名

**重要工作流程：**
当用户要添加新文档时，你应该：
1. 首先使用 check_document_exists 或 search_documents 检查是否已存在相似文档
2. 如果存在相似文档（相似度 > 0.85），询问用户是否要更新现有文档
3. 如果不存在相似文档，则添加新文档
4. 或者直接使用 smart_upsert_document 工具，它会自动完成上述判断

**工具选择指南：**
- check_document_exists: 检查文档是否已存在（推荐在添加前使用）
- smart_upsert_document: 智能添加/更新，自动判断是添加还是更新
- update_document: 当已知文档ID时，更新指定文档
- add_documents: 批量添加多个新文档（不检查重复）
- search_documents: 搜索相关文档，返回ID和相似度

请根据用户的指令选择合适的工具来完成任务。回复时请使用中文，并以友好、专业的方式与用户交互。"""


def agent_node(state: KBManagerState) -> dict:
    """Agent 节点 - 处理用户输入并决定下一步操作"""
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)
    
    messages = state["messages"]
    
    # 如果没有系统消息，添加一个
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
    
    response = llm_with_tools.invoke(messages)
    
    return {"messages": [response]}


def should_continue(state: KBManagerState) -> Literal["tools", "end"]:
    """判断是否需要继续执行工具"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # 如果最后一条消息有工具调用，则继续执行工具
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    return "end"


# ============ 构建 Graph ============
def create_kb_manager_graph():
    """创建知识库管理 Agent Graph"""
    
    # 创建工具节点
    tool_node = ToolNode(tools)
    
    # 构建 Graph
    graph_builder = StateGraph(KBManagerState)
    
    # 添加节点
    graph_builder.add_node("agent", agent_node)
    graph_builder.add_node("tools", tool_node)
    
    # 添加边
    graph_builder.add_edge(START, "agent")
    graph_builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        }
    )
    graph_builder.add_edge("tools", "agent")
    
    # 编译 Graph
    graph = graph_builder.compile()
    
    return graph


# 创建全局 graph 实例
kb_manager_graph = create_kb_manager_graph()


# ============ 便捷调用函数 ============
def run_kb_manager(user_input: str, user_id: str = "default") -> str:
    """
    运行知识库管理 Agent
    
    Args:
        user_input: 用户输入的指令
        user_id: 用户ID
    
    Returns:
        Agent 的回复
    """
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "user_id": user_id,
    }
    
    result = kb_manager_graph.invoke(initial_state)
    
    # 获取最后一条 AI 消息作为回复
    for message in reversed(result["messages"]):
        if isinstance(message, AIMessage):
            return message.content
    
    return "处理完成，但没有生成回复。"


async def arun_kb_manager(user_input: str, user_id: str = "default") -> str:
    """
    异步运行知识库管理 Agent
    
    Args:
        user_input: 用户输入的指令
        user_id: 用户ID
    
    Returns:
        Agent 的回复
    """
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "user_id": user_id,
    }
    
    result = await kb_manager_graph.ainvoke(initial_state)
    
    # 获取最后一条 AI 消息作为回复
    for message in reversed(result["messages"]):
        if isinstance(message, AIMessage):
            return message.content
    
    return "处理完成，但没有生成回复。"


# ============ 测试代码 ============
if __name__ == "__main__":
    
    # 测试用例
    test_queries = [
        "列出所有的知识库集合",
        "创建一个名为 test_kb 的知识库",
        "查看 test_kb 集合的详细信息",
        "在 test_kb 中搜索 '人工智能'",
    ]
    
    print("=" * 60)
    print("知识库管理 Agent 测试")
    print("=" * 60)
    
    for query in test_queries[:1]:  # 只测试第一个查询
        print(f"\n📝 用户输入: {query}")
        print("-" * 40)
        response = run_kb_manager(query)
        print(f"🤖 Agent 回复:\n{response}")
        print("=" * 60)
