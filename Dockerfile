# syntax=docker/dockerfile:1
FROM python:3.14-slim

# uv：与本地开发同源的依赖管理器，保证镜像里装出和 uv.lock 一致的环境
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 先只拷依赖清单再装依赖——代码变更不会打爆 Docker 层缓存
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY main.py ./main.py

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
