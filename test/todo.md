# Bank-copilot Backend Hardening To‑Do (2025-10-31)

面向企业级的后端架构整改清单，按优先级分组，便于逐步实施与追踪。

## 总览目标
- 一致化配置与路由，消除多实现分裂与“示例/生产”混杂。
- 统一异步化数据访问与外部依赖调用策略，提升可靠性与性能。
- 建立最小安全与可观测基线（CORS、JWT、限流、日志、指标、追踪）。
- 补齐自动化测试与 CI/CD，保障持续交付质量。

---

## P0（立即执行）

### 1) 配置与路由一致化
- [ ] 统一配置源，移除/废弃 `app/core/config.py`，全量迁移到 `app/configs/*`（尤其 `agent_config.py`、`db_config.py`、`llm_config.py`）。
	- 验收：所有模块只从 `from app.configs import agent_config as settings` 或对应专用 config 导入；`.env*` 生效，应用可启动。
	- 涉及：`app/main.py`、`app/api/*`、`app/core/*`、`app/utils/*`、`app/pipeline/*`、`README.md`。
- [ ] 集中路由装配：`app/api/router.py` include 所有 v1 路由，并由 `main.py` 用 `settings.API_V1_STR` 统一挂载。
	- 子任务：
		- [ ] include: `v1/agent_v1.py` → `/agent`
		- [ ] include: `v1/chat_v1.py` → `/chat`
		- [ ] include: `v1/doc_parse.py` → `/doc`
		- [ ] include: `v1/insert_v1.py` → `/insert`
		- [ ] include: `v1/search_v1.py` → `/search`
		- [ ] include: `services/auth.py` → `/auth`
		- [ ] 将 `items` 示例路由迁至专用 `test` 路由或测试夹具，避免生产暴露。
	- 验收：`GET /`、`GET /health`、`{API_V1}/agent|chat|doc|insert|search|auth` 正常可达，OpenAPI 文档完整。

	### 2) 数据访问与异步一致性
	- [ ] 选定“全链路 async”方案：
		- [ ] 统一使用 `sqlalchemy[asyncio]` + `sqlmodel` 的 `AsyncSession`。
		- [ ] `app/core/db/postgre.py` 保留一个异步引擎与会话工厂；去除同步 `create_engine` 与混用路径。
		- [ ] `app/core/db/db_services.py` 改造为 async CRUD；不再混用 sync `Session`。
		- [ ] API 层调用统一 `await` 语义。
		- 验收：最小集成测试（创建用户→创建 session→查询 session）在异步路径下通过。

	### 3) 安全基线
	- [ ] CORS：默认不放开，使用环境变量白名单（多环境可区分）。
	- [ ] JWT：密钥只来自环境（KMS/Secrets 管理可作为后续 P2），TTL 适度（默认 1 天），考虑 Refresh Token（可 P1）。
	- [ ] 上传安全：`doc_parse.py` 增加体积上限、MIME 白名单、异常处理；后续考虑扫描/隔离（P1/P2）。
	- [ ] 外部 HTTP 调用（Silicon、DashScope、embeddings）：封装统一客户端，设置超时（默认 10s）、重试（指数退避）、熔断与幂等（必要处）。
	- [ ] 示例凭据与示例路由从生产路径隔离；`fake_secret_token` 移至测试专用模块。
	- 验收：
		- CORS 行为可控；无硬编码秘钥；上传超限/类型不符返回 4xx；外呼失败具备可恢复与告警日志。

	### 4) 可观测性基线
	- [ ] 结构化日志（已具备）模块级 logger 统一导出（`app/core/logger_utils.py`），避免重复初始化。
	- [ ] 请求 ID 中间件：为每个请求注入 `request_id`、`user_id`（如可得）、`session_id` 到日志上下文。
	- [ ] 指标端点 `/metrics`（Prometheus）：请求量/延迟/错误率、外部依赖成功率、DB/缓存连接池指标。
	- [ ] 健康检查：拆分 `liveness` 与 `readiness`，DB/Redis/外部依赖分别检测。
	- 验收：
		- 日志包含 request_id；Prometheus 可抓到指标；`/health`、`/live`、`/ready` 行为符合预期。

	### 5) 容器与环境参数
	- [ ] Docker Compose 使用服务名连接：应用对 Redis/Dragonfly 使用 `dragonfly:6379`，对 PG 使用 `postgres_db:5432`。
	- [ ] 所有连接参数来自环境变量，`configs` 显式解析；本地与容器内取值一致。
	- 验收：容器内/本地均可一键 `docker compose up` 启动全套服务。

---

## P1（两周内）

### 6) RAG/Agent 性能与缓存
- [ ] RAG 结果缓存（query→reranked docs）短期 TTL，命名空间含环境/应用前缀。
- [ ] Dragonfly Key 规范化与 TTL 可配；消息历史按 session 分段与压缩策略（可选）。
- [ ] Agent streaming backpressure 控制与限流（slowapi）。
- 验收：缓存命中提升，端到端 P95 延迟下降（基于测试环境数据）。

### 7) 测试体系补齐
- [ ] 单测：
	- [ ] JWT 工具（签发/验证/异常）；
	- [ ] sanitization；
	- [ ] doc_parse（含安装缺失/错误类型）；
	- [ ] retriever/reranker（可打桩）。
- [ ] 集成测：
	- [ ] 路由 200/401/422；
	- [ ] 流式 SSE；
	- [ ] DB 读写与迁移。
- [ ] E2E：注册→登录→建 session→chat→stream→清理。
- 验收：`pytest` 全绿，基础覆盖率达成（如 60%+ 作为起点）。

### 8) CI/CD 与工程体验
- [ ] GitHub Actions：`uv sync`→`ruff`→`pytest`→Docker 构建→镜像推送（如需要）。
- [ ] pre-commit：ruff、black（可选）、mypy/pyright（至少开启）、大文件与 secrets 检查。
- [ ] Devcontainer/Makefile 与 README 强化（运行、调试、排错指引）。
- 验收：PR 提交自动跑 CI；本地一键脚本可运行常用任务。

---

## P2（一个月）

### 9) 安全与合规深化
- [ ] Secrets 管理（KMS/Hashicorp/Vault），落地密钥轮换流程。
- [ ] API Gateway/WAF，DDoS 防护与 IP 黑白名单策略。
- [ ] 审计日志：管理操作留痕；关键字段脱敏；日志保留与归档策略。
- [ ] 金融行业合规基线（数据分级、访问审计、异常告警、变更审批流程）。

### 10) 可靠性工程
- [ ] 故障演练（DB/Redis/外部 LLM 依赖不可用演练）；
- [ ] SLI/SLO 定义与看板；
- [ ] 回滚策略与蓝绿/金丝雀发布（基础版）。

---

## 文件级改造参考（映射）
- 路由与应用：`app/main.py`、`app/api/router.py`、`app/api/v1/*.py`、`app/api/services/*.py`
- 配置中心：`app/configs/*.py`（agent_config/db_config/llm_config/pipeline_config/app_config）
- 数据访问：`app/core/db/postgre.py`、`app/core/db/db_services.py`
- RAG/Agent：`app/core/agent/**`、`app/core/rag/**`、`app/pipeline/inference_pipeline/**`
- 可观测性：`app/core/logger_utils.py`、新增中间件与 `/metrics` 模块（待建）
- 测试：`test/**`（单测、集成、E2E 目录结构化）
- 部署：`docker-compose.yml`、`README.md`、`.env*`

---

## 快速收益（Quick Wins）
- [ ] 集中路由注册 → 立即提升 API 可用性与文档完整度。
- [ ] 中央化配置导入 → 减少运行期“字段不存在/值不一致”。
- [ ] 统一外呼超时/重试 → 降低外部依赖抖动对服务影响。
- [ ] 增加请求 ID → 日志可关联完整请求链路，便于排障。

---

## 下一步默认执行顺序（建议）
1) P0 全部完成（配置/路由/异步/安全/可观测/容器）。
2) P1 覆盖测试与 CI/CD，上线基础 RAG 缓存与限流。
3) P2 安全/合规与可靠性工程，形成 SLO 与演练机制。

备注：若同意，我可先落地“集中路由注册 + 异步 DB 一致化骨架 + 请求 ID 中间件 + /metrics”的首批改造，并补上最小集成测试。
