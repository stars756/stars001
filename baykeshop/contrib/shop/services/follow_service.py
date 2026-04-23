import logging
from django.core.cache import cache

from baykeshop.contrib.shop.models.goods import BaykeShopGoods, BaykeShopGoodsFollow
from baykeshop.contrib.shop.services.base import UserInteractionServiceBase

logger = logging.getLogger("baykeshop.contrib.shop")


class FollowService(UserInteractionServiceBase):
    """商品关注服务（到货通知/降价通知）— 继承泛型基类"""
    
    MODEL = BaykeShopGoodsFollow
    GOODS_MODEL = BaykeShopGoods
    CACHE_PREFIX = "user_follows"
    ITEM_NAME = "商品"
    ACTION_NAME = "关注"
    
    # Follow 特有：支持 notify_type 过滤
    EXTRA_FILTER_FIELDS_TEMPLATE = {}  # 运行时动态注入 notify_type
    
    logger = logger

    @classmethod
    def _build_filter(cls, user, goods_id, **extra_filters):
        """覆盖：支持 notify_type 动态过滤"""
        f = super()._build_filter(user, goods_id, **extra_filters)
        return f

    # ---- 向后兼容：保留原有方法名，委托给基类 ----

    @classmethod
    def add_follow(cls, user, goods_id, notify_type='arrival'):
        """添加关注（兼容旧接口）"""
        return cls.add(user, goods_id, notify_type=notify_type)

    @classmethod
    def remove_follow(cls, user, goods_id, notify_type=None):
        """取消关注（兼容旧接口）"""
        extra_filters = {}
        if notify_type:
            extra_filters['notify_type'] = notify_type
        return cls.remove(user, goods_id, **extra_filters)

    @classmethod
    def get_user_follows(cls, user, notify_type=None, page_number=1, per_page=20):
        """获取用户关注列表（兼容旧接口）"""
        extra_filters = {}
        if notify_type:
            extra_filters['notify_type'] = notify_type
        
        result = cls.get_list(user, page_number, per_page, **extra_filters)
        return {
            'follows': result.get('follows', []),
            'total': result['total'],
            'page': result['page'],
            'total_pages': result['total_pages'],
        }

    @classmethod
    def is_followed(cls, user, goods_id, notify_type='arrival'):
        """是否已关注（兼容旧接口）— 修复：原版没有缓存，现在通过基类自动获得缓存能力"""
        return cls.is_interacted(user, goods_id, notify_type=notify_type)

    @classmethod
    def get_follows_count(cls, user, notify_type=None):
        """关注总数（兼容旧接口）"""
        extra_filters = {}
        if notify_type:
            extra_filters['notify_type'] = notify_type
        return cls.get_count(user, **extra_filters)

    @classmethod
    def _invalidate_user_follows_cache(cls, user_id):
        """清除缓存（兼容旧接口）— 清除所有类型的缓存"""
        for nt in ['all', 'arrival', 'price_drop']:
            if nt == 'all':
                cls._invalidate_cache(user_id)
            else:
                cls._invalidate_cache(user_id, notify_type=nt)
