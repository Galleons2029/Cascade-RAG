## ExecPlan: 入队前图片 URL 统一处理 + 图像描述替代文本入库（知识库上传链路）

### Summary
在 `markdown` 进入 RabbitMQ 之前，统一处理图片引用，完成三件事：

1. 把 markdown 里的图片 URL 规范化为可访问 URL（相对路径图片先落盘再映射 URL）。
2. 调用专用多模态理解函数生成图片描述（caption）。
3. 重写 markdown 为“保留图片 + 补描述文本”，确保后续文本检索可命中语义，且模型回答时可继续输出 `![caption](url)`。

你已确认的策略：
- 模型链路：OpenAI 兼容 VLM
- 重写格式：保留图片 + 追加描述文本
- 覆盖范围：先覆盖知识库上传主链路
- 失败策略：图片理解失败时降级保留原图
- 输出策略：仅在相关时输出 markdown 图片

---

### Scope
本次只改 `POST /api/v1/knowledge/collections/{collection}/documents` 对应链路，不覆盖 `gradio/chatbot/evaluation` 入口（后续复用同一处理器扩展）。

---

### Public API / Interface Changes
1. 新增静态资源访问接口（用于相对路径图片转可访问 URL）  
`GET /api/v1/knowledge/assets/{doc_id}/{asset_path:path}`

2. 入队消息（`DocumentRawModel`）新增字段：
- `images: list[dict] | None`
每项包含：`url`, `relative_path`, `caption`, `status`

3. 配置新增（`llm_config`）：
- `VISION_CAPTION_MODEL`
- `VISION_CAPTION_MAX_IMAGES`
- `VISION_CAPTION_CONCURRENCY`
- `VISION_CAPTION_TIMEOUT_SEC`
- `VISION_CAPTION_MAX_RETRIES`
- `VISION_CAPTION_PROMPT`（可选，默认内置）
- `PUBLIC_BACKEND_BASE_URL`（无 request 时兜底）

---

### Design

#### 1) 新增统一处理器（入队前）
新增模块：`app/api/services/markdown_image_enricher.py`
核心函数：
- `extract_markdown_and_assets(zip_bytes) -> (markdown_text, assets_map)`
- `resolve_image_url(raw_url, assets_map, doc_id, base_url) -> resolved_url | None`
- `caption_image(url) -> caption`
- `rewrite_markdown_images(markdown_text, mapping) -> rewritten_markdown`
- `build_image_metadata(mapping) -> list[dict]`

重写规则（你已选）：
- 输入：`![](url)`
- 输出：
  - `![<caption>](<resolved_url>)`
  - 紧跟一行纯文本：`图片描述：<caption>（图片URL：<resolved_url>）`
目的：保留可渲染 markdown，同时为向量检索注入纯文本语义。

#### 2) 文档上传服务接入点
修改 [document.py](/Users/apple/PycharmProjects/Cascade-RAG/app/api/services/document.py)：
- 在 `_download_and_publish_result` 中，`_publish_to_queue` 之前调用统一处理器。
- `DocumentUploadTask` 增加 `public_base_url`（从请求注入）。
- `_publish_to_queue` 扩展参数：`images`，并写入 `DocumentRawModel.images`。
- 降级策略：
  - 单图 caption 失败：保留原图 URL，caption 用默认占位（如“图片解析失败”）。
  - 全部图片失败：文档继续入队，不阻塞。

#### 3) 静态图片持久化与访问
- 图片保存目录：`uploads/mineru_assets/{doc_id}/...`
- 新增路由：`knowledge/assets/...` 返回图片文件。
- 必做安全控制：禁止 `..`、绝对路径、越界访问。

#### 4) 清洗阶段保留 URL（关键）
当前清洗会把 URL 替换为 `[URL]`，会破坏“回答继续输出真实图片 URL”的目标。  
修改：
- [cleaning.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/utils/cleaning.py)：`clean_text(..., preserve_urls: bool = False)`
- [cleaning_data_handlers.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/data_logic/cleaning_data_handlers.py)：文档类型调用 `clean_text(..., preserve_urls=True)`；其他类型保持原逻辑。

#### 5) 数据模型透传
- [raw.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/models/raw.py)：`DocumentRawModel` 新增 `images`
- [clean.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/models/clean.py)：`DocumentCleanedModel` 新增 `images`
- [chunk.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/models/chunk.py)：`DocumentChunkModel` 新增 `images`
- [embedding_data_handlers.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/data_logic/embedding_data_handlers.py)：透传 `images`
- [embedded_chunk.py](/Users/apple/PycharmProjects/Cascade-RAG/app/pipeline/feature_pipeline/models/embedded_chunk.py)：写入 payload 的 `metadata.images`

#### 6) 生成侧提示词小改（保证“可输出图片 markdown”）
在 RAG 生成提示增加规则（仅相关时输出）：
- 如果上下文中存在相关 `![caption](url)`，可在答案中保留该 markdown 图片。
- 不相关图片不要输出，避免噪声。
建议修改：
- [rag_agent.py](/Users/apple/PycharmProjects/Cascade-RAG/app/core/agent/graph/rag_agent.py) `generate` 的 PromptTemplate 文本。

---

### Algorithm Details (Decision-Complete)
1. 从 MinerU ZIP 提取 markdown 和资产文件。
2. 解析 markdown 图片标签（去重 URL）。
3. URL 处理：
- `http/https`：直接使用。
- 相对路径：从 ZIP 资产写本地后生成公开 URL。
4. 对每个可访问 URL 调用 VLM caption（并发受限 + 重试）。
5. 重写 markdown：
- `![caption](resolved_url)` + `图片描述：...（图片URL：...）`
6. 组装 `images` 元数据并发布 RabbitMQ。
7. pipeline 清洗时文档保留 URL，不替换 `[URL]`。
8. 入 Qdrant 后检索可命中描述文本，回答时可引用 markdown 图片 URL。

---

### Test Cases
1. ZIP 含 `index.md + images/*.jpg`：
- 入队内容含 `![caption](http...)` 和“图片描述”文本行。
- `images` 元数据完整。
2. markdown 含绝对 URL 图片：
- 不落盘，直接 caption + 重写。
3. 图片 caption 失败：
- 文档仍入队；
- 保留图片 markdown；
- 描述为默认占位。
4. 无图片 markdown：
- 内容不变，链路无回归。
5. 清洗回归：
- 文档 URL 不再被替换成 `[URL]`。
- 非文档类型仍保留原 URL 替换行为。
6. 检索回归：
- `VectorRetriever.rerank` 返回文本中含可用 markdown 图片 URL。
7. 路由安全：
- `assets` 路径穿越请求返回 4xx。

---

### Rollout
1. 先在开发环境开启：
- `VISION_CAPTION_MAX_IMAGES=5`
- `VISION_CAPTION_CONCURRENCY=2`
- 观察延迟与错误率。
2. 监控指标：
- 每文档图片数、caption 成功率、平均处理耗时、降级率。
3. 稳定后再扩展到 `gradio/chatbot/evaluation` 入口，复用同一处理器。

---

### Assumptions & Defaults
1. 使用 OpenAI 兼容视觉模型接口（可接入当前 `ChatOpenAI/init_chat_model` 生态, 模型名改为Qwen/Qwen3-VL-30B-A3B-Instruct即可，base url 不变）。
2. 仅改知识库上传主链路，不做历史回填。
3. 图片处理失败不阻断整文档入库。
4. 仅在答案相关时输出 markdown 图片，不强制全部输出。
