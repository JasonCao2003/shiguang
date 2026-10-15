# Find — 校园失物招领平台（AI Agent）

用语义/多模态匹配把「丢失描述」与「拾获招领」智能配对，并用多智能体完成核验、认领与联系交换。

> 完整需求见 [`docs/PDR.md`](docs/PDR.md)。

## 架构总览

```
前端 Next.js  (Web + 对话 UI + 物品列表)
      │  REST / SSE
后端 FastAPI  (认证、上传、业务 API)
      │
      ├── Agent 层 (LangGraph)
      │     Intake / Matching / Verification / Chat / Coordinator
      │     模型：DeepSeek API（deepseek-flash / deepseek-v4-pro）
      │
      └── 匹配服务
            BGE-M3 向量化 + 召回 (pgvector) + DeepSeek LLM-judge 重排

数据层：Postgres + pgvector · MinIO(图片) · Redis(缓存/队列)
```

- **模型**：DeepSeek API（`deepseek-flash` 多模态 + 文本；`deepseek-v4-pro` 重推理）
- **向量化**：自建 BGE-M3（DeepSeek 不提供 embedding）
- **重排**：DeepSeek `deepseek-flash` LLM-judge
- **范围**：校园；不强制实名；双方自行约定见面；认领成功后 1 周内清理数据。

## 目录结构

```
Find/
├── backend/                 # FastAPI + LangGraph
│   ├── app/
│   │   ├── agents/          # LangGraph 图与节点
│   │   ├── api/v1/          # REST 路由
│   │   ├── core/            # 配置、日志、安全
│   │   ├── db/              # 模型与会话
│   │   ├── schemas/         # Pydantic 模型
│   │   └── services/        # LLM / Embedding / 匹配 / 存储 / 通知
│   ├── alembic/             # 数据库迁移
│   └── pyproject.toml
├── embedding_service/       # BGE-M3 向量化独立服务
├── frontend/                # Next.js
├── docs/PDR.md
└── docker-compose.yml
```

## 快速开始

### 1. 准备环境变量

```bash
cp .env.example .env
# 填入 DEEPSEEK_API_KEY
```

### 2. 启动基础设施（Postgres + pgvector / Redis / MinIO）

```bash
docker compose up -d postgres redis minio
```

### 3. 启动 BGE-M3 向量化服务（首次会下载模型）

```bash
cd embedding_service
uv sync
uv run uvicorn server:app --port 8001
```

### 4. 启动后端

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
# 文档：http://localhost:8000/docs
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000
```

### 全部用 Docker

```bash
docker compose up --build
```

## 开发

```bash
make help      # 查看所有命令
make dev       # 起基础设施 + 后端
make lint      # ruff
make test      # pytest
```

## 实施阶段（对应 PDR §12）

- **M1** 匹配能力验证：登记 → 召回 + 重排 → 候选
- **M2** Agent 化：LangGraph Intake / Matching / Coordinator
- **M3** 对话助手：SSE
- **M4** 安全闭环：核验 + 联系交换 + 争议 HITL
- **M5** 运营：后台 + 数据留存清理 + 评测
