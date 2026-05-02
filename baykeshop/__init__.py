INSTALLED_APPS = [
    'baykeshop.sites.AdminConfig',
    'baykeshop.contrib.shop',
    'baykeshop.contrib.member',
    'baykeshop.contrib.system',
    'baykeshop.contrib.article'
]

# 版本号
__VERSION__ = "1.3.20"

from .celery import app as celery_app

__all__ = ('celery_app',)
