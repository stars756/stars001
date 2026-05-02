import logging
from typing import Any

from django.core.cache import cache
from django.core.paginator import Paginator


class UserInteractionServiceBase:
    """
    泛型"用户-商品"交互服务基类
    
    提供：
    - add / remove CRUD 操作
    - get_list 分页列表（带缓存）
    - is_interacted 存在性检查（带缓存）
    - get_count 计数（带缓存）
    - _invalidate_cache 缓存失效
    """

    # ==================== 子类必须设置 ====================
    MODEL: type[Any] = None           # Django Model 类（如 BaykeShopGoodsFavorite）
    CACHE_PREFIX: str = ""            # 缓存键前缀（如 "user_favorites"）
    ITEM_NAME: str = "项目"            # 中文名称（用于日志和消息，如 "商品"）
    ACTION_NAME: str = "操作"          # 动作名称（如 "收藏"、"关注"）
    GOODS_MODEL: type[Any] = None        # 目标模型类（如 BaykeShopGoods），

    # 字段映射（大多数情况下不需要覆盖）
    USER_FIELD: str = 'user'          # 用户外键字段名
    GOODS_FIELD: str = 'goods'        # 商品外键字段名
    GOODS_ID_FIELD: str = 'goods_id'  # 商品ID字段名（用于 filter）
    EXTRA_FILTER_FIELDS: dict = {}    # 额外的过滤条件（如 Follow 的 notify_type）

    # 缓存配置
    LIST_CACHE_TIMEOUT: int = 30 * 60   # 列表缓存：30分钟
    CHECK_CACHE_TIMEOUT: int = 60       # 存在性检查缓存：1分钟

    logger: Any = None

    @classmethod
    def _get_logger(cls):
        if cls.logger is None:
            cls.logger = logging.getLogger("baykeshop.contrib.shop")
        return cls.logger

    @classmethod
    def _build_filter(cls, user, goods_id, **extra_filters):
        """构建查询过滤条件（自动排除软删除记录）"""
        f = {cls.USER_FIELD: user, cls.GOODS_ID_FIELD: goods_id, 'is_delete': False}
        f.update(cls.EXTRA_FILTER_FIELDS)
        f.update(extra_filters)
        return f

    @classmethod
    def add(cls, user, goods_id, **extra_filters) -> dict:
        """添加交互记录"""
        log = cls._get_logger()
        try:
            goods = cls.GOODS_MODEL.objects.filter(id=goods_id).first()
            if not goods:
                return {'success': False, 'message': f'{cls.ITEM_NAME}不存在'}

            filter_kwargs = cls._build_filter(user, goods_id, **extra_filters)

            obj, created = cls.MODEL.objects.get_or_create(
                defaults={cls.GOODS_FIELD: goods, **extra_filters},
                **filter_kwargs
            )
            if not created:
                return {'success': False, 'message': f'已{cls.ACTION_NAME}过该{cls.ITEM_NAME}'}

            cls._invalidate_cache(user.id, **extra_filters)

            log.info(f"用户 {user.username} {cls.ACTION_NAME}了{cls.ITEM_NAME} {goods.name}")
            return {'success': True, 'message': f'{cls.ACTION_NAME}成功'}

        except Exception as e:
            log.exception(f"{cls.ACTION_NAME}失败: {str(e)}")
            return {'success': False, 'message': f'{cls.ACTION_NAME}失败，请稍后重试'}

    @classmethod
    def remove(cls, user, goods_id, **extra_filters) -> dict:
        """移除交互记录"""
        log = cls._get_logger()
        try:
            filter_kwargs = cls._build_filter(user, goods_id, **extra_filters)
            # Django 4.2+ delete() 返回整数（删除行数），不是元组
            deleted_count = cls.MODEL.objects.filter(**filter_kwargs).delete()

            if deleted_count == 0:
                return {'success': False, 'message': f'未{cls.ACTION_NAME}该{cls.ITEM_NAME}'}

            cls._invalidate_cache(user.id, **extra_filters)

            log.info(f"用户 {user.username} 取消{cls.ACTION_NAME}{cls.ITEM_NAME}ID {goods_id}")
            return {'success': True, 'message': f'取消{cls.ACTION_NAME}成功'}

        except Exception as e:
            log.exception(f"取消{cls.ACTION_NAME}失败: {str(e)}")
            return {'success': False, 'message': '操作失败，请稍后重试'}

    @classmethod
    def get_list(cls, user, page_number=1, per_page=20, **extra_filters) -> dict:
        """获取分页列表（带缓存）"""
        cache_key = cls._cache_key('list', user.id, extra_filters)
        cached = cache.get(cache_key)
        if cached is not None:
            cached_qs = cached
        else:
            qs = cls.MODEL.objects.filter(**{cls.USER_FIELD: user})
            qs = qs.filter(**extra_filters) if extra_filters else qs
            cached_qs = list(
                qs.select_related(cls.GOODS_FIELD)
                .values('id', cls.GOODS_ID_FIELD, f'{cls.GOODS_FIELD}__name', 'created_time')
                .order_by('-created_time')
            )
            cache.set(cache_key, cached_qs, timeout=cls.LIST_CACHE_TIMEOUT)

        paginator = Paginator(cached_qs, per_page)
        page_obj = paginator.get_page(page_number)

        list_key = cls.ACTION_NAME.lower() + 's'
        return {
            list_key: list(page_obj),
            'total': paginator.count,
            'page': page_number,
            'total_pages': paginator.num_pages,
        }

    @classmethod
    def is_interacted(cls, user, goods_id, **extra_filters) -> bool:
        """是否存在交互记录（带缓存）"""
        cache_key = cls._cache_key('check', user.id, {**extra_filters, 'gid': goods_id})
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        filter_kwargs = cls._build_filter(user, goods_id, **extra_filters)
        exists = cls.MODEL.objects.filter(**filter_kwargs).exists()
        cache.set(cache_key, exists, timeout=cls.CHECK_CACHE_TIMEOUT)
        return exists

    @classmethod
    def get_count(cls, user, **extra_filters) -> int:
        """获取总数（带缓存）"""
        cache_key = cls._cache_key('count', user.id, extra_filters)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        qs = cls.MODEL.objects.filter(**{cls.USER_FIELD: user})
        qs = qs.filter(**extra_filters) if extra_filters else qs
        count = qs.count()
        cache.set(cache_key, count, timeout=cls.CHECK_CACHE_TIMEOUT)
        return count

    @classmethod
    def _invalidate_cache(cls, user_id, **extra_filters):
        """清除相关缓存"""
        cache.delete(cls._cache_key('list', user_id, extra_filters))
        cache.delete(cls._cache_key('count', user_id, extra_filters))

    @classmethod
    def _cache_key(cls, suffix: str, user_id: int, extra_filters: dict = None) -> str:
        """构建缓存键"""
        if extra_filters:
            filter_str = ":".join(f"{k}:{v}" for k, v in sorted(extra_filters.items()))
            return f"{cls.CACHE_PREFIX}:{suffix}:{user_id}:{filter_str}"
        return f"{cls.CACHE_PREFIX}:{suffix}:{user_id}"
