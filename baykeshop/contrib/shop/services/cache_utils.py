"""缓存工具 — CacheableService Mixin 提供通用的带锁缓存查询能力"""

import logging
import random
import time
from typing import Callable
from django.core.cache import cache

logger = logging.getLogger("baykeshop.contrib.shop")


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

        result = query_fn()
        data = list(result) if not isinstance(result, list) else result

        if data:
            cache.set(cache_key, data, timeout=timeout)
        else:
            cache.set(cache_key, [], timeout=null_timeout)

        return data
