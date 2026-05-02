# ============================================================
# BaykeShop Dockerfile — 生产级多阶段构建
# Python 3.11-slim + Gunicorn + Celery
# ============================================================

# ---- 阶段 1: 基础依赖安装（利用 Docker 缓存层） ----
FROM python:3.11-slim as base

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖（PostgreSQL 客户端、编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd -r baykeuser && useradd -r -g baykeuser -d /app -s /sbin/nologin baykeuser

WORKDIR /app

# 先复制 requirements.txt（Docker 缓存优化：pip 层只在依赖变化时重建）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后复制 baykeshop 本地包源码（含 setup.py）
COPY baykeshop/ baykeshop/
RUN pip install --no-cache-dir -e ./baykeshop

# ---- 阶段 2: 运行时镜像（更小） ----
FROM python:3.11-slim as runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 运行时只需 PostgreSQL 客户端库（不需要编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 base 阶段复制已安装的 Python 包
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# 创建非 root 用户
RUN groupadd -r baykeuser && useradd -r -g baykeuser -d /app -s /sbin/nologin baykeuser

WORKDIR /app

# 复制项目代码
COPY --chown=baykeuser:baykeuser . .

# 收集静态文件（在 USER 切换前，确保有写权限）
RUN python manage.py collectstatic --noinput

# 创建必要目录并设置权限
RUN mkdir -p logs media uploads \
    && chown -R baykeuser:baykeuser logs media static uploads

# 切换到非 root 用户运行
USER baykeuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/ || exit 1

# 默认启动命令（可被 docker-compose 覆盖）
CMD ["gunicorn", "project.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "gthread", \
     "--threads", "4", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
