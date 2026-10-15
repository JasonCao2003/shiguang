.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## 显示所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## 从模板创建 .env
	@test -f .env || cp .env.example .env
	@echo ".env ready"

.PHONY: infra
infra: env ## 启动基础设施 (postgres/redis/minio)
	$(COMPOSE) up -d postgres redis minio

.PHONY: infra-down
infra-down: ## 停止基础设施
	$(COMPOSE) down

.PHONY: embed
embed: ## 启动 BGE-M3 向量化服务
	cd embedding_service && uv sync && uv run uvicorn server:app --reload --port 8001

.PHONY: api
api: env ## 启动后端
	cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

.PHONY: dev
dev: infra ## 起基础设施 + 后端
	$(MAKE) api

.PHONY: web
web: ## 启动前端
	cd frontend && npm install && npm run dev

.PHONY: migrate
migrate: ## 执行数据库迁移
	cd backend && uv run alembic upgrade head

.PHONY: revision
revision: ## 生成迁移 (ARGS="-m 'msg'")
	cd backend && uv run alembic revision --autogenerate $(ARGS)

.PHONY: lint
lint: ## 代码检查
	cd backend && uv run ruff check . && uv run ruff format --check .

.PHONY: fmt
fmt: ## 代码格式化
	cd backend && uv run ruff check --fix . && uv run ruff format .

.PHONY: test
test: ## 运行测试
	cd backend && uv run pytest

.PHONY: up
up: env ## 全部 Docker 启动
	$(COMPOSE) up --build
