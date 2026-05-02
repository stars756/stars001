"""
Django settings for project project.

环境变量通过 .env 文件管理（python-decouple），
.env.example 为模板文件，.env 为实际配置（已 gitignore）。
"""
import os
import baykeshop
from pathlib import Path
from django.urls import reverse_lazy
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

LOGIN_URL = reverse_lazy('member:login')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

# 生产环境保护：使用默认 SECRET_KEY 时拒绝启动，强制通过 .env 配置
if not DEBUG and SECRET_KEY == 'django-insecure-dev-key-change-in-production':
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        '生产环境必须设置 SECRET_KEY，请在 .env 中配置随机密钥。\n'
        '生成方式: python -c "import secrets; print(secrets.token_urlsafe(50))"'
    )

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# ============================================================
# 生产环境安全设置（Nginx 反向代理终止 TLS，需设置 PROXY_SSL_HEADER）
# ============================================================
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# 通用安全头（所有环境生效）
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True


# Application definition

INSTALLED_APPS = [
    # django.contrib.admin 被 baykeshop.sites.AdminConfig 替代（自定义 AdminSite）
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 需要依赖站点系统
    'django.contrib.sites',
    'rest_framework',
    # drf-spectacular: OpenAPI/Swagger 文档
    # 'drf_spectacular.frontend',   # Swagger UI + ReDoc 通过 URL 路由提供，不需在 INSTALLED_APPS 中注册
    *baykeshop.INSTALLED_APPS,
]

# 配置站点系统ID（`django.contrib.sites`）
SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='shop_db'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 300,
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'static'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# DRF 全局配置
REST_FRAMEWORK = {
    # OpenAPI Schema 生成器
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # 认证方式：Session + 可选 JWT（预留）
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    # 权限
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # 分页
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # 全局限流（默认：已登录用户120次/分钟）
    'DEFAULT_THROTTLE_CLASSES': [
        'baykeshop.api.throttles.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # 普通用户默认：120次/分钟（足够正常浏览和操作）
        'user': '120/min',
        # 敏感接口（注册/登录/短信/邮箱验证）：10次/分钟, 30次/小时
        'sensitive': '10/min',
        # 写操作（订单/购物车/评论）：20次/分钟
        'write': '20/min',
        # 文件上传：5次/分钟（资源消耗大）
        'upload': '5/min',
    },
}

# Redis 基础 URL（可通过环境变量覆盖）
REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379')

# 1. 缓存配置
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'{REDIS_URL}/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# 2. 会话存储到Redis
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Celery 中间人（单独用2号数据库存任务队列）
CELERY_BROKER_URL = f'{REDIS_URL}/2'
# Celery 结果存储
CELERY_RESULT_BACKEND = f'{REDIS_URL}/3'
# 任务序列化格式
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
# 时区
CELERY_TIMEZONE = 'Asia/Shanghai'
# 禁用UTC（避免时区错乱）
CELERY_ENABLE_UTC = False
# 可靠性配置：Worker 完成后才确认，崩溃不丢任务
CELERY_TASK_ACKS_LATE = True
# Worker 失联自动重新入队
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# 任务结果 1 小时后过期，避免 Redis 内存泄漏
CELERY_RESULT_EXPIRES = 3600

# ---- 开发环境：同步执行任务，日志直接回 runserver 终端 ----
# DEBUG=True 时 .delay() 变成同步调用，邮件 print() 在当前终端可见
# 需要测异步时在 .env 里设 CELERY_ALWAYS_EAGER=False 再手启 Worker
CELERY_TASK_ALWAYS_EAGER = config('CELERY_ALWAYS_EAGER', default=DEBUG, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True  # 任务异常直接抛出，方便调试

# Flower 监控配置（启动: celery -A baykeshop flower --port=5555 --basic_auth=admin:changeme）
FLOWER_PORT = 5555
FLOWER_BASIC_AUTH = config('FLOWER_BASIC_AUTH', default='admin:changeme')

# Celery Beat 定时任务调度配置
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    # 每5分钟检查并自动关闭超时未支付订单（默认30分钟超时）
    'auto-close-expired-orders': {
        'task': 'baykeshop.auto_close_expired_orders',
        'schedule': 300,  # 每5分钟 = 300秒
        'options': {'queue': 'periodic'},
    },
    # 每天凌晨1点生成前一天销售统计快照
    'daily-order-statistics': {
        'task': 'baykeshop.daily_order_statistics',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': 'periodic'},
    },
    # 每10分钟预热首页热点数据缓存
    'cache-warmup-homepage': {
        'task': 'baykeshop.cache_warmup_homepage',
        'schedule': 600,  # 每10分钟 = 600秒
        'options': {'queue': 'periodic'},
    },
    # 每小时清理过期的邮箱验证Token（兜底）
    'cleanup-expired-tokens': {
        'task': 'baykeshop.cleanup_expired_tokens',
        'schedule': crontab(minute=0),  # 每小时整点
        'options': {'queue': 'periodic'},
    },
}
# 订单超时自动关闭的阈值（分钟），可通过 BAYKE_SETTINGS 覆盖
ORDER_EXPIRE_MINUTES = 30


# 开发环境使用ConsoleBackend
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ============================================================
# drf-spectacular OpenAPI 文档配置
# ============================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'BaykeShop 电商系统 API',
    'DESCRIPTION': (
        '基于 Django REST Framework 的 B2C 电商系统后端接口文档。\n\n'
        '**功能模块：**\n'
        '- 商品管理（SPU/SKU/分类/搜索）\n'
        '- 购物车 CRUD\n'
        '- 订单管理（创建/支付/取消/确认收货）\n'
        '- 用户中心（资料/地址/SMS验证/邮箱验证）\n'
        '- 图片上传\n'
        '- 订单评论\n\n'
            '**认证方式：** Session 认证（登录后访问）\n\n'
            '**技术栈：** Django 4.2 + DRF + PostgreSQL + Redis + Celery'
    ),
    'VERSION': '1.3.20',
    'SERVE_INCLUDE_SCHEMA': False,  # 不在根路径展示 schema JSON
    # API 标签分组
    'TAGS': [
        {'name': '购物车', 'description': '商品购物车增删改查'},
        {'name': '订单', 'description': '订单创建、支付、取消'},
        {'name': '支付', 'description': '支付宝订单支付接口'},
        {'name': '用户', 'description': '用户信息、地址管理'},
        {'name': '安全', 'description': '邮箱验证、短信验证码、个人资料更新'},
        {'name': '上传', 'description': '图片上传'},
        {'name': '评论', 'description': '订单评价'},
    ],
    # 组件 Schema 配置
    'SCHEMA_PATH_PREFIX': '/api/',
    'COMPONENT_SPLIT_REQUEST': True,
}

# ============================================================
# 统一日志配置（LOGGING dictConfig）
# ============================================================
import os

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # ---- 格式化器 ----
    'formatters': {
        # 开发环境：带颜色的详细输出
        'verbose': {
            'format': '[{levelname:<8} {asctime}] {module}:{funcName}:{lineno} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        # 生产环境：结构化风格，方便 ELK/日志平台采集
        # 注意：避免在 format 字符串中混用 JSON 引号和 {style} 字段，Python 3.13 会误解析
        'structured': {
            'format': '[{asctime}] {levelname:>8} | {name}:{module}:{funcName}:{lineno} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
        },
        # 简洁模式
        'simple': {
            'format': '[{levelname}] {name}: {message}',
            'style': '{',
        },
    },

    # ---- 处理器（Handler） ----
    'handlers': {
        # 控制台输出（开发环境用）
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'level': 'DEBUG',
        },
        # 主日志文件（按日期轮转）
        'file_general': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'baykeshop.log'),
            'when': 'midnight',       # 每天午夜轮转
            'interval': 1,
            'backupCount': 30,         # 保留30天
            'encoding': 'utf-8',
            'formatter': 'structured',
            'level': 'INFO',
        },
        # 错误日志（单独文件，方便监控报警）
        'file_error': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
            'when': 'midnight',
            'interval': 1,
            'backupCount': 60,          # 错误日志保留更久
            'encoding': 'utf-8',
            'formatter': 'structured',
            'level': 'ERROR',
        },
        # 安全日志（敏感操作单独记录）
        'file_security': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'security.log'),
            'when': 'midnight',
            'interval': 1,
            'backupCount': 90,          # 安全日志保留90天（审计需求）
            'encoding': 'utf-8',
            'formatter': 'structured',
            'level': 'INFO',
        },
    },

    # ---- 日志记录器（Logger） ----
    'loggers': {
        # ===== 商城核心模块 =====
        'baykeshop.contrib.shop': {
            'handlers': ['console', 'file_general'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # ===== 安全审计日志（独立文件） =====
        'baykeshop.security': {
            'handlers': ['console', 'file_security'],
            'level': 'INFO',
            'propagate': False,
        },
        # ===== 会员/安全模块 =====
        'baykeshop.contrib.member': {
            'handlers': ['console', 'file_general', 'file_security'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # ===== Celery 定时任务 =====
        'baykeshop.periodic_tasks': {
            'handlers': ['console', 'file_general'],
            'level': 'INFO',
            'propagate': False,
        },
        # ===== Django 内置 =====
        # Django 请求异常（404、500等）单独记录到错误日志
        'django.request': {
            'handlers': ['console', 'file_error'],
            'level': 'WARNING',
            'propagate': True,
        },
        # 数据库查询日志（仅 DEBUG 模式开启）
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # DRF 异常
        'rest_framework': {
            'handlers': ['console', 'file_general'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Celery Worker
        'celery': {
            'handlers': ['console', 'file_general'],
            'level': 'INFO',
            'propagate': False,
        },
    },

    # ===== 根 Logger =====
    'root': {
        'level': 'WARNING',
        'handlers': ['console', 'file_error'],
    },
}

# 确保 logs 目录存在
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


