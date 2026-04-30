"""
BaykeShop 测试配置

- 缓存后端覆盖为 LocMemCache，避免依赖 Redis
- 其他全局测试 fixtures
"""

import django
from django.conf import settings


def _override_cache():
    """将默认缓存后端改为本地内存缓存，避免测试依赖 Redis"""
    if 'default' in settings.CACHES:
        settings.CACHES['default'] = {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache',
        }


def pytest_configure():
    _override_cache()


# Django 应用配置加载后覆盖缓存
_override_cache()
