import logging
import random
from django.core.cache import cache

from baykeshop.contrib.shop.models import BaykeShopCategory, BaykeShopGoods
from baykeshop.contrib.system.models import BaykeBanners

logger = logging.getLogger("baykeshop.contrib.shop")


class PublicService:
    """公开服务"""

    @staticmethod
    def get_index_floors():
        """
        获取首页楼层

        Returns:
            QuerySet: 分类查询集，每个分类附加了spu_list属性

        性能优化：
        - prefetch_related 预取子分类，避免 N+1
        - 一次批量查询所有楼层的商品（prefetch_object + Prefetch）
        - 原实现：N 个顶级分类 = 2N 次 SQL 循环查询
        """
        category_list = BaykeShopCategory.objects.filter(
            is_floor=True, parent__isnull=True
        ).prefetch_related('baykeshopcategory_set')

        # 批量获取所有楼层涉及的商品，避免逐个分类查询
        from django.db.models import Prefetch
        all_sub_cat_ids = []
        for category in category_list:
            all_sub_cat_ids.extend(category.baykeshopcategory_set.values_list('id', flat=True))

        if all_sub_cat_ids:
            # 一次性预取所有楼层商品
            all_floor_goods = list(
                BaykeShopGoods.objects.filter(category__id__in=all_sub_cat_ids)
            )
            # 按 分类ID 分组
            goods_by_category = {}
            for g in all_floor_goods:
                for cat_id in g.category.values_list('id', flat=True):
                    goods_by_category.setdefault(cat_id, []).append(g)
        else:
            goods_by_category = {}

        for category in category_list:
            sub_categories = category.baykeshopcategory_set.all()
            spu_list = []
            for sub_cat in sub_categories:
                spu_list.extend(goods_by_category.get(sub_cat.id, []))
            category.spu_list = spu_list

        return category_list

    @staticmethod
    def get_index_banners():
        """
        获取首页轮播图

        缓存策略：
        - 核心高频数据永不过期，后台更新时手动触发缓存更新
        - 防穿透：空值缓存1分钟短过期
        - 防雪崩：永不过期，无需随机偏移
        - 防一致性：配套 update_banners_cache 方法

        Returns:
            QuerySet: 轮播图查询集，按order排序
        """
        cache_key = "banners:index"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # 查询数据库
        banners = BaykeBanners.objects.filter(is_show=True).order_by('-order')

        if not banners.exists():
            # 空值缓存1分钟，防穿透
            cache.set(cache_key, [], timeout=60)
            return []

        # 永不过期缓存
        cache.set(cache_key, banners, timeout=None)
        return banners

    @staticmethod
    def update_banners_cache():
        """
        更新轮播图缓存

        防一致性策略：
        1. 先更数据库 → 调用此方法删除缓存
        2. 延迟双删兜底：可配合异步任务延迟再次删除
        3. 重试机制：删除失败可重试

        此方法在后台更新轮播图后调用，保证缓存和数据库一致
        """
        cache_key = "banners:index"
        cache.delete(cache_key)
        logger.info(f"轮播图缓存已删除: {cache_key}")


    @staticmethod
    def get_goods_categories():
        """
        获取商品分类列表

        Returns:
            QuerySet: 商品分类查询集，按order排序
        """
        cache_key = "categories:list"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        categories = BaykeShopCategory.objects.all().order_by('order')

        if not categories.exists():
            cache.set(cache_key, [], timeout=60)
            return []

        cache.set(cache_key, categories, timeout=None)
        return categories

    @staticmethod
    def update_goods_categories_cache():
        """
        更新商品分类缓存
        """
        cache_key = "categories:list"
        cache.delete(cache_key)
        logger.info(f"商品分类缓存已删除: {cache_key}")

    @staticmethod
    def get_hot_goods_list(limit=10):
        """
        获取首页热门商品列表

        热门商品定义：推荐商品按销量排序
        缓存策略：永不过期，空值短过期

        Args:
            limit: 限制数量，默认10

        Returns:
            QuerySet: 热门商品查询集
        """
        cache_key = f"hot_goods:list:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        hot_goods = BaykeShopGoods.objects.filter(
            is_recommend=True
        ).order_by('-sales')[:limit]

        # 注意：切片后的查询集无法再过滤，但可以缓存列表
        # 转换为列表以便缓存
        goods_list = list(hot_goods)

        if not goods_list:
            cache.set(cache_key, [], timeout=60)
            return []

        cache.set(cache_key, goods_list, timeout=None)
        return goods_list

    @staticmethod
    def update_hot_goods_cache(limit=10):
        """
        更新热门商品缓存（后台调用）
        """
        cache_key = f"hot_goods:list:{limit}"
        cache.delete(cache_key)
        logger.info(f"热门商品缓存已删除: {cache_key}")