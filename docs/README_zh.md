# Bank-copilot：面向银行财务管理的开源 LLM 智能体平台

一个可用于生产的 LangGraph 智能体平台，帮助银行构建可扩展、安全、易维护的 AI 代理服务。


## 🌟 功能亮点

- **生产级架构**

  - FastAPI 提供高性能异步 API
  - 集成 LangGraph 构建智能体工作流
  - 接入 Langfuse 实现 LLM 可观测性与监控
  - 不同环境下的结构化日志
  - PostgreSQL 负责数据持久化
  - 支持 Docker 与 Docker Compose 部署


## 🚀 快速开始

### 依赖要求

- Python 3.11+
- PostgreSQL（参考下方[数据库配置](#数据库配置)）
- Docker 与 Docker Compose（可选）


### 环境配置
1. 克隆仓库：

```bash
git clone https://github.com/Galleons2029/Bank-copilot.git
cd Bank-copilot
```

2. 创建并激活虚拟环境：


#### 使用 uv
进入项目目录后执行：
```bash
uv sync   # 若尚未安装 uv，可先运行 "pip install uv"
``` 
自动同步项目依赖。

### 数据库配置

1. 创建 PostgreSQL 数据库（Supabase 或本地实例均可）。
2. 在根目录 `.env` 文件中更新数据库连接串：

```bash
POSTGRES_URL="postgresql+psycopg_async://:your-db-password@POSTGRES_HOST:POSTGRES_PORT/POSTGRES_DB"
```

3. 启动 Qdrant：
```bash
data run -p 6333:6333 -p 6334:6334 \
    -v "$(pwd)/qdrant_storage:/qdrant/storage:z" \
    qdrant/qdrant
```

RabbitMQ：
#### RabbitMQ 4.x 最新版
```bash
data run -it --rm --name rabbitmq \
    -p 5672:5672 -p 15672:15672 \
    rabbitmq:4-management
```

### 使用 Docker Compose 部署
```bash
data compose up
```



## API KEY 配置

所有敏感凭据放置在项目根目录的 `.env` 文件中，与 `.env.example` 处于同一级目录。

在仓库根目录执行：
```bash
cp .env.example .env
```
然后按照下述提示填写对应凭据即可。
