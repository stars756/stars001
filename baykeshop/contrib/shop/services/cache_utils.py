"""
缓存工具 — 统一 11+ 处重复的 cache-get/check-null/set 模式

提供两种使用方式：
1. 函数式：cache_query(key_fn, query_fn, timeout)
2. 类方法 Mixin：继承 CacheableService 即可获得 _cached_get / _cached_list 方法
"""

import logging
import random
import time
from typing import Any, Callable, Optional, TypeVar
from functools import wraps
from django.core.cache import cache

logger = logging.getLogger("baykeshop.contrib.shop")

T = TypeVar('T')


def cache_query(
    key_fn: Callable[..., str],
    query_fn: Callable[[], T],
    timeout: int = 1800,
    null_timeout: int = 60,
) -> T:
    """
    缓存查询装饰器/函数
    
    统一处理：缓存命中 → 直接返回；未命中 → 查DB → 写缓存 → 返回
    自动处理空值防穿透（null_timeout 短过期）
    
    Args:
        key_fn: 缓存键生成函数（无参，返回字符串）
        query_fn: 数据库查询函数（无参，返回数据或 None）
        timeout: 正常数据缓存时间（秒），默认 30 分钟
        null_timeout: 空值缓存时间（秒），默认 1 分钟（防穿透）
    
    Returns:
        查询结果（可能为 None）
    
    示例：
        def get_banners():
            return cache_query(
                key_fn=lambda: "banners:index",
                query_fn=lambda: list(BaykeBanners.objects.filter(is_show=True).order_by('-order')),
                timeout=None,  # 永不过期
            )
    """
    cache_key = key_fn()
    
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__NULL__" else None

    data = query_fn()

    if data:
        # 防雪崩：基础超时 + 随机偏移
        actual_timeout = (
            timeout
            if timeout is None or not isinstance(timeout, int) or timeout <= 0
            else timeout + random.randint(60, 300) if timeout > 300 else timeout
        )
        cache.set(cache_key, data, timeout=actual_timeout)
    else:
        cache.set(cache_key, "__NULL__", timeout=null_timeout)

    return data


class CacheableService:
    """可缓存服务 Mixin — 提供通用的带锁缓存查询能力"""

    @staticmethod
    def _exponential_backoff(max_retries=3, base_delay=0.1):
        """指数退避重试生成器"""
        for retry in range(max_retries):
            yield
            if retry < max_retries - 1:
                delay = min(base_delay * (2 ** retry), 1.0)
                time.sleep(delay)

    @classmethod
    def _cached_get_with_lock(
        cls,
        cache_prefix: str,
        pk,
        model_class,
        default=None,
        lock_timeout=10,
        base_cache_timeout=1800,
        null_cache_timeout=60,
    ):
        """
        带分布式锁的通用缓存获取（防击穿 + 防穿透 + 防雪崩）
        
        原本 get_goods_detail() 和 get_goods_spu_detail() 各写了一遍 ~65 行相同逻辑，
        现在统一为此方法。
        
        Args:
            cache_prefix: 缓存键前缀（如 "goods_detail" / "goods_spu_detail"）
            pk: 主键 ID
            model_class: Django Model 类
            default: 可选的默认值（如果提供且 DB 未查到则缓存此值）
            lock_timeout: 锁超时时间（秒）
            base_cache_timeout: 正常数据基础缓存时间（秒）
            null_cache_timeout: 空值缓存时间（秒）
        
        Returns:
            Model 实例或 None
        """
        if not pk:
            return None

        cache_key = f"{cache_prefix}:{pk}"
        lock_key = f"{cache_prefix}_lock:{pk}"

        # 尝试从缓存获取
        cached = cache.get(cache_key)
        if cached is not None:
            return cached if cached != "__NULL__" else None

        # 获取分布式锁，防击穿
        lock_acquired = cache.add(lock_key, "1", timeout=lock_timeout)
        if not lock_acquired:
            for _ in cls._exponential_backoff():
                cached = cache.get(cache_key)
                if cached is not None:
                    return cached if cached != "__NULL__" else None

        try:
            # 查询数据库
            data = default if default is not None else None
            if default is None:
                try:
                    data = model_class.objects.get(id=pk)
                except model_class.DoesNotExist:
                    data = None

            # 设置缓存（含防雪崩随机偏移）
            if data:
                total_timeout = base_cache_timeout + random.randint(60, 300)
                cache.set(cache_key, data, timeout=total_timeout)
            else:
                cache.set(cache_key, "__NULL__", timeout=null_cache_timeout)

            return data
        finally:
            if lock_acquired:
                cache.delete(lock_key)

    @classmethod
    def invalidate(cls, cache_prefix, pk):
        """清除指定前缀+ID 的缓存"""
        cache_key = f"{cache_prefix}:{pk}"
        cache.delete(cache_key)
        logger.info(f"缓存已删除: {cache_key}")

    @classmethod
    def cached_list(
        cls,
        cache_prefix: str,
        query_fn: Callable[[], list],
        timeout: int = 1800,
        null_timeout: int = 60,
    ) -> list:
        """
        缓存列表查询
        
        用于 banners、categories、hot_goods 等列表型数据的统一缓存。
        
        Args:
            cache_prefix: 缓存键前缀
            query_fn: 无参查询函数，返回 list 或 QuerySet
            timeout: 正常缓存时间
            null_timeout: 空值缓存时间
        
        Returns:
            列表数据
        """
        cache_key = cache_prefix
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        data = list(query_fn()) if not isinstance(query_fn(), list) else query_fn()

        if data:
            cache.set(cache_key, data, timeout=timeout)
        else:
            cache.set(cache_key, [], timeout=null_timeout)

        return data
