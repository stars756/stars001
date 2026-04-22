#!/bin/bash
# ============================================================
# BaykeShop Docker 快速启动脚本
#
# 使用方式:
#   ./docker/start.sh          # 开发环境一键启动
#   ./docker/start.sh prod     # 生产环境（含 Nginx + HTTPS）
#
# 前置条件:
#   1. 已安装 Docker 和 Docker Compose V2
#   2. 已复制并配置: cp .env.example .env
# ============================================================

set -e

echo "============================================"
echo "  BaykeShop Docker 部署脚本"
echo "============================================"

PROFILE="${1:-dev}"
ENV_FILE=".env"

# 检查 .env 文件是否存在
if [ ! -f "$ENV_FILE" ]; then
    echo "[INFO] 未找到 .env 文件，从模板创建..."
    cp .env.example "$ENV_FILE"
    echo ""
    echo "⚠️  请先编辑 .env 文件，填入正确的配置值！"
    echo "   重点修改项："
    echo "   - POSTGRES_PASSWORD（数据库密码）"
    echo "   - SECRET_KEY（Django 密钥）"
    echo "   - ALIPAY_* （支付宝配置）"
    echo ""
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker Desktop"
    exit 1
fi

case $PROFILE in
    prod)
        echo "[PROD] 生产环境模式启动..."
        docker compose --profile prod up -d --build

        echo ""
        echo "✅ 生产环境已启动！"
        echo "   Web:      http://localhost (Nginx)"
        echo "   API文档:  https://yourdomain.com/api/docs/"
        echo ""
        echo "   常用命令:"
        echo "   docker compose logs -f web           # 查看 web 日志"
        echo "   docker compose logs -f celery-worker # 查看 Celery 日志"
        ;;

    dev|*)
        echo "[DEV] 开发环境模式启动..."
        docker compose up -d --build

        echo ""
        echo "✅ 开发环境已启动！"
        echo "   Web 服务:  http://localhost:8000"
        echo "   API文档:   http://localhost:8000/api/docs/"
        echo "   ReDoc文档: http://localhost:8000/api/redoc/"
        echo "   Swagger:   http://localhost:8000/api/schema/"
        echo ""
        echo "   数据库:    localhost:5432 (用户: baykeuser)"
        echo "   Redis:     localhost:6379"
        echo ""
        echo "   常用命令:"
        echo "   docker compose up -d              # 后台启动全部服务"
        echo "   docker compose logs -f            # 查看所有日志"
        echo "   docker compose exec web python manage.py shell  # Django Shell"
        echo "   docker compose exec postgres psql -U baykeuser -d baykeshop  # 数据库 CLI"
        echo "   docker compose down               # 停止并删除容器"
        echo "   docker compose down -v            # 停止并删除卷（⚠️ 会丢失数据！）"
        ;;
esac

echo ""
echo "============================================"
echo "  首次部署请执行数据库迁移:"
echo "  docker compose exec web python manage.py migrate"
echo "  docker compose exec web python manage.py createsuperuser"
echo "  docker compose exec web python manage.py collectstatic --noinput"
echo "============================================"
