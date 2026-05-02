import logging

from django.core.cache import cache

from baykeshop.contrib.shop.models.goods import BaykeShopGoods, BaykeShopGoodsFavorite
from baykeshop.contrib.shop.services.base import UserInteractionServiceBase

logger = logging.getLogger("baykeshop.contrib.shop")


class FavoriteService(UserInteractionServiceBase):
    """商品收藏服务 — 继承泛型基类，只需定义元数据"""

    MODEL = BaykeShopGoodsFavorite
    GOODS_MODEL = BaykeShopGoods
    CACHE_PREFIX = "user_favorites"
    ITEM_NAME = "商品"
    ACTION_NAME = "收藏"

    logger = logger

    # ---- 向后兼容：保留原有方法名，委托给基类 ----

    @classmethod
    def add_favorite(cls, user, goods_id):
        """添加收藏（兼容旧接口）"""
        return cls.add(user, goods_id)

    @classmethod
    def remove_favorite(cls, user, goods_id):
        """取消收藏（兼容旧接口）"""
        return cls.remove(user, goods_id)

    @classmethod
    def get_user_favorites(cls, user, page_number=1, per_page=20):
        """获取用户收藏列表，含商品完整信息（图片/价格），2分钟缓存"""
        cache_key = f"{cls.CACHE_PREFIX}:detail_list:{user.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from django.core.paginator import Paginator
        favorites = BaykeShopGoodsFavorite.objects.filter(
            user=user
        ).select_related('goods').order_by('-created_time')
        total = favorites.count()
        paginator = Paginator(favorites, per_page)
        page_obj = paginator.get_page(page_number)

        items = []
        for fav in page_obj:
            goods = fav.goods
            items.append({
                'id': fav.id,
                'goods_id': goods.id,
                'goods_name': goods.name,
                'goods_price': float(getattr(goods, 'price', 0) or 0),
                'image_url': str(getattr(goods, 'image_url', '') or ''),
            })

        result = {
            'favorites': items,
            'total': total,
            'page': page_number,
            'total_pages': paginator.num_pages,
        }
        cache.set(cache_key, result, timeout=120)
        return result

    @classmethod
    def is_favorited(cls, user, goods_id):
        """是否已收藏（兼容旧接口）"""
        return cls.is_interacted(user, goods_id)

    @classmethod
    def get_favorites_count(cls, user):
        """收藏总数（兼容旧接口）"""
        return cls.get_count(user)

    @classmethod
    def _invalidate_user_favorites_cache(cls, user_id):
        """清除缓存（兼容旧接口）"""
        cls._invalidate_cache(user_id)
        cache.delete(f"{cls.CACHE_PREFIX}:detail_list:{user_id}")
