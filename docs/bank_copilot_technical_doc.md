# Bank-Copilot 技术方案白皮书

适用范围：企业财务智能体项目（Bank-Copilot）立项评审、实施交付、运行维护。本文基于 `agent-chat-ui/public/uploads/intro.md`、`docs/intro.md` 以及源代码当前实现编制，覆盖系统背景、业务需求、总体架构、数据/模型治理、部署与安全策略，确保方案满足企业级交付标准。

---

## 1. 项目概述

### 1.1 业务背景
- 苏州银行账务管理存在**新员工入门难、分录穿透检索慢、总分不平定位慢**三大痛点，需构建面向财会场景的交互式智能体（`docs/intro.md`），以释放 2 亿+分户余额、1 亿+会计分录、700 万+交易明细、60 万+总分核对数据价值。
- 项目命名“账策云帆 Bank-Copilot”，目标是在“训-检-析”全链路提供由大模型驱动的助手能力，实现**术语问答、分层查询、异常推理**三个核心任务。

### 1.2 建设目标与关键指标
| 任务 | 指标 | 说明 |
| --- | --- | --- |
| 员工培训智能体 | 结构化知识库覆盖率 ≥95%，响应延迟 ≤ 2s | 通过多模态课程、问答测评帮助新人 5 天内完成上岗培训 |
| 多轮检索问答 | 20+ 轮对话意图连续率 ≥90%，记忆检索准确率 ≥92% | 结合层次化记忆与知识图谱动态建模，实现跨维度追问 |
| 总分不平推理 | 推理准确率 ≥80%，单轮推理耗时 ≤500ms | 对接账务流水、核对结果，生成诊断原因与补救方案 |

---

## 2. 业务能力与用户场景
1. **非财会人员入门**：通过术语学习、案例引导、测评闭环降低培训成本（`agent-chat-ui/public/uploads/intro.md`）。
2. **会计管理人员查询**：在同一对话内同时追踪日期、机构、币种、科目等维度，实现“从分录到明细”穿透检索。
3. **财务稽核定位**：输入“总分不平”提示，即可获取该科目的日期/机构/金额回溯及可能原因，辅助复核。

Stakeholder：财务共享中心、运营管理部、内审稽核、IT 运维。

---

## 3. 系统总体架构

### 3.1 分层视图
```
┌─────────────┐
│ 终端用户    │  财会人员/培训管理员/审计
└──────┬──────┘
       │Next.js (agent-chat-ui)
┌──────▼──────┐
│ 前端交互层  │ 多场景会话、报表、可视化
└──────┬──────┘
       │HTTPS / WebSocket
┌──────▼──────┐
│ API 服务层  │ FastAPI + LangGraph API (`app/main.py`)
└──────┬──────┘
       │LangGraph SDK / REST
┌──────▼────────┐
│ 智能体编排层  │ LangGraph 多Agent、ReasoningPipeline
└──────┬────────┘
       │工具链调用
┌──────▼─────────────────────┐
│ 数据 & 知识底座            │ PostgreSQL, Qdrant, FalkorDB/Neo4j, RabbitMQ, Dragonfly
└───────────────────────────┘
```

### 3.2 组件清单
| 层级 | 关键组件 | 代码/配置 | 说明 |
| --- | --- | --- | --- |
| API 网关 | FastAPI, Langfuse, CORS | `app/main.py`, `app/api/router.py` | 对外统一鉴权、限流、健康检查，支持 Langfuse 可观测性 |
| 智能体编排 | LangGraph Agent | `app/core/agent/graph/chief_agent.py` | ChatOpenAI + 工具编排 + Postgres Checkpoint |
| 推理引擎 | ReasoningPipeline | `app/pipeline/inference_pipeline/reasoning.py` | 可开关 RAG、包含 Query Expansion / Rerank |
| RAG 检索 | VectorRetriever | `app/core/rag/retriever.py` | 多查询扩展、Qdrant 多租户检索、重排 |
| 数据摄取 | Bytewax Streaming | `app/pipeline/feature_pipeline/main.py` | MQ→清洗→切分→嵌入→Qdrant |
| 知识图谱 | Graphiti + Neo4j | `app/core/kg/data_ingest.py` | 层次化记忆+结构化记忆融合 |
| 存储 | PostgreSQL, Qdrant, FalkorDB, Dragonfly | `docker-compose.yml` | 分别承载会话/检查点、向量、图谱缓存、运行态状态 |
| UI | Next.js + LangGraph SDK | `agent-chat-ui/package.json` | 提供聊天、图表、课程展示 |

---

## 4. 核心功能模块

### 4.1 员工交互式培训
- 基于开源 LLM 解析 PDF/Word，自动生成课程结构与测评（`agent-chat-ui/public/uploads/intro.md`）。
- 支持“Learn + Build”双轨教学、AI 生成内容需人工审核，嵌入幻灯片/音频/思维导图，多模态呈现（`docs/intro.md`）。
- 教学流程：资料解析→课程编排→多模态产出→测评→学习进度追踪，后台记录偏好用于个性化推送。

### 4.2 多层检索问答
- 多维度对话意图持续化：结合层次化记忆与结构化知识图谱（`docs/intro.md`），4 通道混合召回（关系/实体/原始片段/主题集群）。
- LangGraph Agent 通过 Postgres Checkpoint 保存会话状态，支持 20+ 轮上下文（`app/core/agent/graph/chief_agent.py`）。

### 4.3 总分不平推理
- ReasoningPipeline 结合 RAG 上下文对单科目进行追溯，输出原因及建议（`app/pipeline/inference_pipeline/reasoning.py`）。
- 目标：准确率≥80%，500ms 内完成多步追踪（`docs/intro.md`），必要时切换为启发式解释或请求更多参数。

### 4.4 数据分析智能体
- 在隔离“沙盒”中进行数据分析，确保运行安全（`docs/intro.md`）。
- 提供 OLAP 查询（FalkorDB/Fast图数据库 + Qdrant 向量），实现毫秒级多跳检索。

---

## 5. 数据与知识工程

### 5.1 数据源与采集
- 来源：账务底表、培训手册、业务制度、知识问答记录等；支持多格式（Word、PDF、Excel、JSON、图像）。
- 通过 `publish_to_rabbitmq` 将上传文档/交易记录写入 MQ（`app/core/mq.py`，`app/evaluation/doc_parse.py`）。

### 5.2 流式摄取管道
1. **消息输入**：Bytewax `RabbitMQSource` 读取 MQ，具备快照、飞行消息管理（`app/pipeline/feature_pipeline/data_flow/stream_input.py`）。
2. **原始建模**：`RawDispatcher` 按类型构建 DataModel（`app/pipeline/feature_pipeline/data_logic/dispatchers.py`）。
3. **清洗**：`CleaningDispatcher` 调用不同 Handler 做文本清洗、OCR、去噪。
4. **分块**：`ChunkingDispatcher` + `chunk_text`（递归 + token 拆分）生成语义块，保留 overlap（`app/pipeline/feature_pipeline/utils/chunking.py`）。
5. **嵌入**：`EmbeddingDispatcher` 调 Silicon Embedding API 生成向量（`app/pipeline/feature_pipeline/utils/embeddings.py`）。
6. **落库**：`QdrantOutput` 将清洗数据、向量写入不同集合，实现多租户/知识库隔离（`app/pipeline/feature_pipeline/data_flow/stream_output.py`）。

该流程在 `app/pipeline/feature_pipeline/main.py` 以 Dataflow 方式串联，可横向扩展。

### 5.3 知识图谱与记忆
- Graphiti + Neo4j 构建具时间维度的记忆节点，自动标记有效/失效时间（`app/core/kg/data_ingest.py`）。
- 采用“层次化记忆 + 结构化记忆”策略：原始对话→事实提炼→三元组写入 KG，提供多通道检索（`docs/intro.md`）。
- 结合 FalkorDB（`docker-compose.yml`）保证图数据毫秒级查询与租户隔离。

### 5.4 数据质量与治理
- 清洗、切分、嵌入步骤均输出日志，利用 structlog 写入 JSONL（`app/core/logger_utils.py`）。
- 通过 `app/configs/pipeline_config.py` 将 MQ/Qdrant/Embedding 参数集中管理，支持多环境切换。
- 配置多模型校验、去重、过期更新策略，确保知识库可信。

---

## 6. 智能体与推理引擎

### 6.1 LangGraph 编排
- `LangGraphAgent` 负责组装聊天节点、工具节点、条件跳转，并使用 Postgres Checkpoint (`app/core/agent/graph/chief_agent.py`)。
- 工具体系目前包含 DuckDuckGo 检索，可扩展财务系统 API（`app/core/agent/tools/__init__.py`）。
- 通过 `GraphState` 保持消息 + session_id，支持 UUID / 自定义 ID 校验（`app/models/graph.py`）。

### 6.2 推理与 RAG
- ReasoningPipeline：构造系统 prompt + 用户 prompt，按需开启 RAG；当 `enable_rag=True` 时走**多查询扩展→检索→重排**链路（`app/pipeline/inference_pipeline/reasoning.py`）。
- Query Expansion、Self Query、Reranker 模块分别负责生成多视角 query、提取 metadata、重排（`app/core/rag/query_expansion.py`, `app/core/rag/self_query.py`, `app/core/rag/reranking.py`）。
- `VectorRetriever` 使用 ThreadPool 批量对不同集合搜索，支持 metadata filter 与多集合并行（`app/core/rag/retriever.py`）。

### 6.3 记忆与上下文管理
- 使用 Psycopg 连接池 / AsyncPostgresSaver 记录 LangGraph state（`app/core/agent/graph/chief_agent.py`，`app/configs/agent_config.py`）。
- JWT 结合 session 生成访问 token，支持线程级鉴权（`app/utils/auth.py`）。

### 6.4 模型与参数
- LLM、Embedding、Rerank 均由 `app/configs/llm_config.py` 管理，支持 SiliconFlow、OpenAI、自托管模型动态切换。
- 默认 LLM：Qwen/Qwen3-8B or GPT-4o-mini；Embedding：BAAI/bge-m3；Rerank：bge-reranker-v2-m3。

---

## 7. API 服务设计

### 7.1 FastAPI 网关
- `app/main.py` 提供根路由与 `/health`，在 lifespan 中初始化数据库服务；整合 CORS、Langfuse（`app/api/dependency.py`）。
- `app/api/router.py` 汇总 `/api/v1/inference`、样例 REST 端点，并在启动时连接 Postgres。
- `app/api/v1/inference_v1.py` 通过 ReasoningPipeline 对外暴露推理接口。

### 7.2 数据持久化与会话管理
- `app/core/db/db_services.py` 采用 SQLModel + AsyncSession 操作 User/Session；`app/core/db/postgre.py` 封装 AsyncEngine/Session。
- 配置项 (`app/configs/db_config.py`) 支持本地/TimescaleDB/云 Postgres。

### 7.3 安全与限流
- AgentConfig (`app/configs/agent_config.py`) 定义多环境参数、日志、JWT、限流策略。
- `app/utils/auth.py` 对 thread_id 生成 JWT token，`verify_token` 保障格式合法。
- 默认 CORS `*`，生产建议由 `ALLOWED_ORIGINS` 限制；后续可接入 API Gateway/WAF。

---

## 8. 前端与体验

- `agent-chat-ui` 基于 Next.js 16、React 19、Tailwind、LangGraph SDK 构建（`agent-chat-ui/package.json`）。
- 主要功能：多会话面板、LangGraph 流式消息、图表/报表组件（echarts/recharts）、Mermaid/Markdown 渲染、暗黑模式。
- Supabase 集成用于用户态同步/鉴权，支持自托管或 SaaS。
- `.env` (`agent-chat-ui/.env`) 提供 API URL、Assistant ID、Supabase Key，前端通过 `.env` 与 LangGraph API 互通。

---

## 9. 基础设施与部署

### 9.1 服务编排
`docker-compose.yml` 启动 MQ（RabbitMQ 4.x 管控台）、Qdrant、Postgres、Dragonfly、FalkorDB、Feature Pipeline、后端 FastAPI、LangGraph API、前端。特性：
- 通过 env_file 复用 `.env`；Feature Pipeline/Backend 依赖 MQ+Qdrant。
- LangGraph API 暴露 2024 端口，Dragonfly 提供 Redis 兼容态。
- 支持本地开发与服务器部署，亦可迁移至 K8s（建议以 Helm 拆分 Stateful/Stateless）。

### 9.2 配置管理
- 所有模块使用 `pydantic-settings` 读取 `.env`（`app/configs/*.py`）。
- `pyproject.toml` 定义 Python 3.12+ 依赖，包含 FastAPI、LangGraph、Graphiti、Qdrant、Langfuse 等企业级组件。

### 9.3 运维与弹性
- RabbitMQ：启用持久化队列、连接池（`app/core/mq.py`）。
- Qdrant：向量集合按“clean / vector / knowledge_id”命名隔离，多租户安全。
- Graphiti/FalkorDB：提供租户隔离，保障多智能体同时访问时无冲突（`docs/intro.md`）。
- Postgres：建议启用 WAL 备份与连接池监控。

---

## 10. 安全、合规与治理
- **身份鉴权**：JWT + Session ID；可叠加企业 IAM、SAML。
- **数据隔离**：知识库按 `knowledge_id` 切分集合，图数据库提供租户实例；RabbitMQ queue per data domain。
- **数据治理**：清洗/切分/嵌入过程记录来源、哈希、时间戳，实现可追溯。
- **权限控制**：关键操作需用户确认（“人机协同办公，规范 AI 权限”，`docs/intro.md`）。
- **隐私保护**：上下文压缩、噪声过滤，避免无关数据进入模型窗（`docs/intro.md`）。
- **安全审计**：Langfuse 与 structlog JSONL 提供 API 访问、模型调用日志，满足监管留痕。

---

## 11. 观测、测试与质量保证
- **日志**：structlog 输出控制台 + JSONL 文件；按环境分文件名（`app/core/logger_utils.py`）。
- **监控**：Langfuse 记录 LLM 调用、token、延迟；健康检查 `/health` 包含数据库状态（`app/main.py`）。
- **评测**：计划使用 ragas、openevals、内部评测脚本评估问答质量（`pyproject.toml` 依赖）。
- **数据回放**：Bytewax + RabbitMQ snapshot 支持失败重放；Doc Parse 脚本可模拟文档上传（`app/evaluation/doc_parse.py`）。
- **模型治理**：ReasoningPipeline 支持 mock 模式、Evaluation API，用于 A/B 测试与上线闸门。

---

## 12. 交付路线与下一步

| 阶段 | 时间 | 里程碑 | 关键输出 |
| --- | --- | --- | --- |
| 需求梳理 | W1-W2 | 完成业务问题拆解、数据清单 | 精益画布、数据映射 |
| 基础设施 & 管道 | W3-W6 | MQ/Qdrant/Postgres/Graphiti 上线，Bytewax 流水线投产 | 数据摄取脚本、监控看板 |
| 智能体能力 | W5-W10 | LangGraph 多 Agent、ReasoningPipeline 联调 | 意图追踪、推理引擎、RAG 指标 |
| 前端与验收 | W9-W12 | Next.js UI、权限策略、E2E 验收 | 用户手册、部署手册、验收报告 |
| 运营优化 | 持续 | 数据闭环、模型迭代 | 评测报告、监控策略 |

后续工作建议：
1. **扩展多模态能力**：接入 OCR/表格解析工具，覆盖更多账务单证。
2. **强化安全隔离**：结合企业 AD/零信任，实现多租户账号管控。
3. **自动化评测**：通过 ragas/自建数据集形成 Regression Suite，保障版本升级质量。
4. **集成业务系统**：将推理结果回写核心账务系统/自动工单，形成闭环。

---

## 附录：关键文件映射
- 背景/需求：`docs/intro.md`、`agent-chat-ui/public/uploads/intro.md`
- 架构/配置：`app/main.py`、`app/configs/*.py`、`docker-compose.yml`
- 智能体：`app/core/agent/graph/chief_agent.py`、`app/core/agent/tools/*`
- 推理/RAG：`app/pipeline/inference_pipeline/*`、`app/core/rag/*`
- 数据管道：`app/pipeline/feature_pipeline/*`、`app/core/mq.py`
- 存储：`app/core/db/*`
- 前端：`agent-chat-ui/*`

本文档将随代码迭代进行版本更新，建议纳入 CI 文档检查流程，确保技术与实现保持一致。

