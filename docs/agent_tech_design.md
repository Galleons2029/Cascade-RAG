# MiniCascade-RAG 智能体技术设计文档（完整版）

本文档基于当前核心实现（`app/core/agent/graph/*.py`）与相关配置，系统化说明端到端智能体方案：输入 → 解析 → 检索 → 规划 → 校验 → 呈现，并补充架构、数据契约、序列流程、可观测性、安全与部署测试策略。面向研发与运维人员，作为设计说明与扩展参考。

更新时间：2025-10-29

---

## 1. 目标与范围

- 目标
  - 将自然语言问题转化为基于知识与数据的可验证答案，支持检索增强（RAG）、SQL 自动生成与多智能体并行研究。
  - 保证可追溯、可审计、可迭代，便于在生产环境落地。

- 范围
  - 涵盖对话/流式生成、检索、SQL 生成与校验、并行研究编排、会话与状态持久化、可观测性与安全建议。
  - 接口层与 UI 仅给出对接要点（工程细节见 `app/` 与 `ui/`）。

---

## 2. 架构总览

组件（逻辑分层）：
- 接入层：API/WS 与 UI（`app/main.py`, `app/api/*`, `ui/*`）。
- 主管代理（Chief Agent）：`chief_agent.LangGraphAgent`
  - 构建 LangGraph（LLM 节点、Tool 节点、条件边），统一回调与状态持久化（Postgres Checkpointer）。
- RAG 智能体：`rag_agent.rag_agent`
  - 工具规划 → 检索（Qdrant）→ 相关性判定 → 改写/生成回答。
- SQL 智能体：`sql_graph.sql_graph_test`
  - 拆解 → 生成子 SQL → 执行 → 合并 → 校验 → 必要时重写迭代。
- 多智能体监督：`supervisor.supervisor_agent`
  - 监督模型通过工具调用并行触发多个研究进程（RAG Agent），汇总研究笔记。
- 存储与基础设施
  - 向量库：Qdrant（`app/core/rag/retriever.py`）。
  - 关系库：PostgreSQL（业务数据 + LangGraph Checkpointer）。
  - 可观测性：Langfuse（回调 `CallbackHandler`）+ 应用日志（`logger_utils.py`）。

关键交互（高层序列）：
1) 用户问题 → Chief Agent → LangGraph（LLM → Tool → LLM...）→ 结果返回/流式返回；
2) 若走 RAG：Agent → retrieve_content → grade_documents →（generate | rewrite）；
3) 若走 SQL：write_query → execute_query → check_query →（END | rewrite 循环）；
4) 若启多智能体：Supervisor → think_tool/ConductResearch → 并行 rag_agent → 汇总 ToolMessage → 决策。

---

## 3. 输入（Stage 0）

用户输入与系统上下文：
- 用户问题（question）：必填，自然语言。
- 可选上下文（context）：场景、时间、业务域、历史摘要等。
- 会话与身份（session）：`session_id`、`user_id`，贯穿状态与权限。

数据契约（Input Contract）
- Input
  - question: string
  - context?: { scene?: string, timeRange?: string | {start: string, end: string}, domain?: string }
  - session: { session_id: string, user_id?: string }
- Output（进入解析阶段）
  - normalized_query: string（可结合历史进行轻量归一化）
  - context: 同上

代码映射
- `chief_agent.LangGraphAgent.get_response/get_stream_response`
  - 注入 `CallbackHandler`、`config.configurable.thread_id=session_id`、`metadata`；
  - 若 `_graph` 未创建则 `create_graph()`，并使用 `AsyncPostgresSaver` 建立 Checkpointer。

---

## 4. 阶段1（解析）：意图/实体/指标/过滤条件抽取

目标
- 将问句结构化为意图、实体、指标（含口径）、过滤条件、维度与时间范围，便于检索与 SQL 规划。

现状
- 改写与工具规划
  - `rag_agent.agent` 通过 `bind_tools(tools)` 决策是否使用 `retrieve_content`。
  - `rag_agent.rewrite` 在检索不相关时重写问题，提升语义明确度。
  - `langgraph.prebuilt.tools_condition` 用于路由（继续工具 or 结束）。
- 多智能体
  - `supervisor.supervisor` 使用 `lead_researcher_prompt` 结合工具（`think_tool`, `ConductResearch`）决定研究计划。

建议的结构化输出（可选增强）
- 以 Pydantic / JSON Schema 约束模型输出：
  - intent: string
  - entities: string[]
  - metrics: { name: string, spec?: string, agg?: 'sum'|'avg'|'count'|... }[]
  - filters: { field: string, op: '='|'in'|'between'|'>'|'>='|'<'|'<='|'like', value: any }[]
  - dims?: string[]
  - time_range?: { start?: string, end?: string, grain?: 'day'|'week'|'month' }
  - rewritten_query?: string

边界与异常
- 空/含糊问题：触发澄清/重写；
- 大量实体/复杂过滤：分治成子问题（交由 SQL 智能体或 Supervisor）。

---

## 5. 阶段2（检索）：混合检索目录、口径、样例 SQL、图谱路径

目标
- 召回支撑回答的“证据与规范”：目录（术语/字段）、指标口径、样例 SQL、知识/数据图谱路径。

实现现状
- 语义检索
  - `rag_agent.retrieve_content` 调用 `VectorRetriever`：Qdrant `retrieve_top_k(k=4)` → `rerank(keep_top_k=3)`；
  - 嵌入：`OpenAIEmbeddings`（通过 SiliconFlow 代理；模型 `BAAI/bge-m3`）。
- 相关性判定
  - `rag_agent.grade_documents` 使用 LLM 对检索上下文与问题做二分类（yes/no），决定走 `generate` 还是 `rewrite`。
- 规范与路径
  - 代码中未显式维护“口径/目录/图谱”仓；建议将规范文档片段化入库，并带上类型与域标签。

混合检索建议（可渐进落地）
- 语义向量 + BM25（关键词）双通道，使用 RRF 融合；
- 元数据过滤（域、时间、权限、来源可靠级别）；
- 规范类文档优先：通过字段加权或独立候选池；
- 图谱路径：以图数据库或文档化关系描述检索到相关路径片段。

输出契约（Retrieve Contract）
- contexts: Doc[]（含类型：catalog|caliber|sample_sql|graph_path；source、chunk_id、score）
- decision: 'retrieve' | 'no_retrieve' | 'rewrite'
- relevance_score?: number

失败与回退
- 未召回：降级为澄清/重写；
- Qdrant 不可用：可退化为 BM25 或缓存。

---

## 6. 阶段3（规划）：基于模板与图谱生成候选 SQL / 调用链

目标
- 结合解析与检索结果、数据库 Schema/目录/口径，生成可执行的 SQL 或工具调用链。

SQL 智能体（`sql_graph.py`）
- 拆解：`DECOMPOSE_QUESTION_PROMPT` → 子问题列表；
- 子问题 SQL：`WRITE_QUERY_PROMPT` + `get_table_info()`（实时读取 PG `information_schema.columns`）；
- 执行：`QuerySQLDatabaseTool` 针对每个子 SQL 执行，保留结果片段；
- 合并：`MERGE_RESULTS_PROMPT` 合成最终 SQL；
- 执行最终 SQL：`execute_query`；
- 校验：`CHECK_QUERY_PROMPT`（结合执行结果）；
- 重写：`REWRITE_QUERY_PROMPT` 循环，`should_continue` 控制 ≤ 5 轮。
- 解析 SQL 代码块：`parse_query` 抽取 ```sql```

RAG 调用链（`rag_agent.py`）
- `START → agent → tools_condition → retrieve → grade_documents → (generate | rewrite) → agent ...`
- `generate` 使用 `PromptTemplate` 进行基于上下文的回答，未知即“我不知道”。

多智能体研究（`supervisor.py`）
- 监督节点 `supervisor` 决策；
- `supervisor_tools` 将 `ConductResearch` 工具并行分发到多个 `rag_agent.ainvoke`；
- 子结果以 `ToolMessage` 回注，`get_notes_from_tool_calls` 汇总研究笔记。

输出契约（Plan Contract）
- candidate_sql?: string
- call_chain: string[]（节点/工具轨迹）
- research_notes?: string[]

异常与边界
- Schema 漂移：`get_table_info()` 应加入缓存/超时与失败回退；
- 执行错误：保留错误信息并引导 `rewrite_query`；
- 超大问题：拆解为多子问题并设并发上限。

---

## 7. 阶段4（校验）：权限 / 口径一致性 / 结果取样

目标
- 在返回前从安全与正确性双维度进行审查，减少幻觉与越权风险。

现状
- 语义/执行校验：`check_query` + `truncate_execuion`；
- 迭代修正：`rewrite_query`；
- 通过/终止：`should_continue`（迭代次数或判定正确）。

待补能力（建议实施）
- 权限校验
  - 按 `user_id` 绑定数据库角色或逻辑视图（RLS/CLS），`QuerySQLDatabaseTool` 前执行鉴权；
  - 限制只读白名单语句（SELECT），拒绝 DDL/DML；
  - 审计：记录执行 SQL、行数、耗时与调用方。
- 口径一致性
  - 校对 SQL 中指标字段/聚合与“口径目录”定义；
  - 生成答案时附口径定义与版本；
  - 口径变更需版本化，前后兼容期内给出提示。
- 结果取样
  - 随机/分层样本与历史统计对比；
  - 阈值或异常检测（如 3σ）告警。

输出契约（Validate Contract）
- validated: boolean
- issues?: { type: 'permission'|'caliber'|'semantic'|'outlier', detail: string }[]
- rewritten_sql?: string

---

## 8. 阶段5（呈现）：指标解释 / 过程溯源 / 图表渲染

目标
- 交付可读答案与结构化数据，并能追溯来源与过程，支持图表可视化。

现状
- 文本答案：`rag_agent.generate`；
- 溯源：
  - LangGraph 状态持久化（`AsyncPostgresSaver`）与 `get_chat_history`/`clear_chat_history`；
  - 研究笔记：`get_notes_from_tool_calls` 汇总 `ToolMessage`；
  - 建议 UI 展示：命中的文档片段、SQL 摘要、节点轨迹与评分。
- 可视化建议
  - 结构化 Payload：`{ text, charts?: [{type, spec, data}], provenance, metrics_explained }`；
  - 前端可用 vega-lite/ECharts；提供“下载 CSV/SQL”。

---

## 9. 可观测性与运维

- 追踪与指标
  - Langfuse：`CallbackHandler` 已在 `chief_agent`/`rag_agent` 接入；
  - 日志：`logger_utils` 记录模型、重试、连接池等关键事件；
  - 建议补充：检索召回/重排得分、SQL 执行耗时/行数、判定结果（grade_documents）分布。
- 重试与降级
  - `chief_agent._chat`：对 `OpenAIError` 有按环境的重试与模型回退（生产可切备用模型）；
  - 连接池建立失败：生产环境可无 Checkpointer 继续运行（有日志告警）。
- 健康检查
  - Qdrant/PG 可加开机与定时探活；
  - Langfuse 回调失败不影响主流程，但需记录。

---

## 10. 配置与安全

环境变量（建议，不要硬编码）：
- LLM 与 Embedding
  - LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
  - EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
- Qdrant
  - QDRANT_HOST / QDRANT_PORT / QDRANT_API_KEY?
- PostgreSQL
  - POSTGRES_URL 或 PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD
  - POSTGRES_POOL_SIZE、连接超时
- LangGraph / Langfuse
  - CHECKPOINTER_*（沿用 POSTGRES_*）
  - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST

安全基线
- 严禁在代码中硬编码密钥（当前仓库存在示例值，务必改为读取环境变量）。
- SQL 执行：仅允许 SELECT；参数化与白名单化；限制最大行数与超时。
- 文档权限：检索结果按租户/角色过滤；payload 不泄漏敏感元数据。

---

## 11. 性能与容量规划

- 并发与队列
  - `supervisor` 并行研究上限：`max_concurrent_researchers`；
  - 建议对检索与 SQL 执行加并发限流与超时（不同域不同阈值）。
- 缓存
  - `get_table_info()` 与目录/口径文档可加缓存；
  - 检索前加 Query 缓存（短时）以提高复问与类问响应。
- 资源与成本
  - 开发/生产分环境模型参数（`Environment`），生产提高质量设置，开发降低成本（top_p、温度、tokens）。

---

## 12. 部署与运行（建议）

- 依赖
  - Docker Compose（仓库已有 `docker-compose.yml`）
  - 环境变量文件 `.env`：包含上述配置项。
- 运行要点
  - 在 Postgres 准备好后首次启动会自动创建 Checkpointer 表（由 `AsyncPostgresSaver.setup()` 完成）。
  - 确保 Qdrant 集合（如 `zsk_test1`）与嵌入模型可用。
- 观测与日志
  - 打通 Langfuse 项目；
  - 将应用日志收集到集中平台（如 Loki/ELK）。

---

## 13. 测试策略

- 单元测试
  - 解析：结构化解析 Schema（一旦实现）输入输出比对；
  - 检索：在小样本 Qdrant 上验证召回与 `grade_documents` 判定；
  - SQL：对 `parse_query`、`get_table_info`、`should_continue` 进行边界测试；
  - 多智能体：`supervisor_tools` 并行聚合的正确性（数量、顺序、失败容忍）。
- 集成测试
  - 端到端问答（RAG/SQL 各 1-2 条 happy path + 失败回退用例）。
- 评测与对比
  - `evaluation/` 提供的模拟与日志可扩展为回归评测基线。

---

## 14. 常见问题与故障排查

- LLM 超时/报错：查看 `chief_agent` 重试与降级日志，确认密钥与 base_url；
- Qdrant 召回为空：确认集合/向量维度与模型匹配，检查过滤条件；
- SQL 执行错误：查看 `execute_query` 的具体异常，确认字段/表名与权限；
- 会话状态缺失：确认 Postgres 可用且 Checkpointer 已开启；生产若无 Checkpointer，状态不可回放属预期。

---

## 15. 术语表

- 口径（Caliber）：指标的统一统计口径与解释规范。
- 目录（Catalog）：字段/表/指标的组织与释义。
- 溯源（Provenance）：生成答案所依赖的证据、工具与流程轨迹。

---

## 16. 附录：关键文件映射

- `app/core/agent/graph/chief_agent.py`：核心对话代理，构建 LangGraph、绑定工具、持久化状态、会话管理。
- `app/core/agent/graph/rag_agent.py`：RAG 工作流（agent/检索/重写/生成/相关性判定）。
- `app/core/agent/graph/sql_graph.py`：SQL 规划流水线（拆解/生成/执行/校验/重写）。
- `app/core/agent/graph/supervisor.py`：多智能体监督与并行研究。
- `app/core/rag/retriever.py`：向量检索器（Qdrant）。
- `app/core/logger_utils.py`：结构化日志。
- `app/configs/*`：模型、数据库、向量库与管线配置。

---

## 17. 小结与后续路线

当前系统已具备：
- RAG：检索→相关性→改写/生成的闭环；
- SQL：拆解→生成→执行→校验→重写的可迭代链路；
- 多智能体：监督并行研究与研究笔记汇总；
- 状态：基于 Postgres 的会话级持久化与回放；
- 观测：Langfuse 回调与应用日志。

优先级建议：
1) 秘钥配置去硬编码，全面改用环境变量；
2) 引入“口径/目录”规范仓与一致性校验；
3) 权限模型与 SQL 执行白名单；
4) 检索混合策略与缓存；
5) 呈现层的可视化规范与过程溯源面板。