"""
API 限流策略 — 防刷、防滥用

分层限流设计：
1. 全局默认限流：普通用户 120次/分钟
2. 敏感接口限流（注册/短信/登录）：10次/分钟, 30次/小时
3. 写操作限流（订单/购物车）：60次/分钟

使用方式（在视图上）:
    from baykeshop.api.throttles import (
        SensitiveRateThrottle,
        WriteOperationThrottle,
    )

    class MyView(APIView):
        throttle_classes = [SensitiveRateThrottle]   # 敏感接口用严格限流
        # 或
        throttle_classes = [WriteOperationThrottle]   # 写操作用中等限流

全局默认在 REST_FRAMEWORK 配置 DEFAULT_THROTTLE_CLASSES 和 DEFAULT_THROTTLE_RATES。
"""

import time
from rest_framework.throttling import SimpleRateThrottle


class _IdentThrottle(SimpleRateThrottle):
    """通用限流基类 — 按 user.id 或 IP 生成 cache key"""
    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR', 'unknown')
            ident = f"ip:{ip}"
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class UserRateThrottle(_IdentThrottle):
    """
    [全局默认] 按用户限流

    已登录用户按 user.id 限流，
    未登录用户按 IP 地址限流。
    """
    scope = 'user'


class SensitiveRateThrottle(_IdentThrottle):
    """
    [敏感接口] 严格限流 — 用于注册、登录、短信发送、邮箱验证等接口
    限制：每分钟 10 次
    """
    scope = 'sensitive'


class WriteRateThrottle(_IdentThrottle):
    """
    [写操作] 中等限流 — 用于订单创建、购物车添加、评论等接口
    限制：每分钟 20 次
    """
    scope = 'write'


WriteOperationThrottle = WriteRateThrottle


class UploadRateThrottle(_IdentThrottle):
    """
    [上传接口] 限流 — 文件上传资源消耗大
    限制：每分钟 5 次
    """
    scope = 'upload'
