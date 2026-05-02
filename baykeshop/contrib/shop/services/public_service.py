import logging

from django.core.cache import cache

from baykeshop.contrib.shop.models import BaykeShopCategory, BaykeShopGoods
from baykeshop.contrib.system.models import BaykeBanners

logger = logging.getLogger("baykeshop.contrib.shop")


class PublicService:
    """公开服务"""

    _FLOORS_CACHE_KEY = "floors:index"
    _FLOORS_CACHE_TTL = 600  # 10 分钟，与 Celery 预热频率一致

    _BANNERS_CACHE_KEY = "banners:index"
    _BANNERS_CACHE_TTL = 3600  # 1 小时兜底，后台变更时主动失效
    _BANNERS_NULL_TTL = 60  # 空值防穿透

    @staticmethod
    def get_index_floors():
        """
        获取首页楼层（Redis 缓存，Celery 定时预热）

        Returns:
            QuerySet: 分类查询集，每个分类附加了spu_list属性

        性能优化：
        - Redis 缓存 10 分钟，Celery 每 10 分钟预热
        - prefetch_related 预取子分类，避免 N+1
        - 一次批量查询所有楼层的商品
        - 原实现：N 个顶级分类 = 2N 次 SQL 循环查询
        """
        cached = cache.get(PublicService._FLOORS_CACHE_KEY)
        if cached is not None:
            return cached

        category_list = BaykeShopCategory.objects.filter(
            is_floor=True, parent__isnull=True
        ).prefetch_related('baykeshopcategory_set')

        # 批量获取所有楼层涉及的商品，避免逐个分类查询
        all_sub_cat_ids = []
        for category in category_list:
            all_sub_cat_ids.extend(category.baykeshopcategory_set.values_list('id', flat=True))

        if all_sub_cat_ids:
            # 一次性预取所有楼层商品
            all_floor_goods = list(
                BaykeShopGoods.objects.raw().filter(category__id__in=all_sub_cat_ids)
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

        cache.set(PublicService._FLOORS_CACHE_KEY, category_list, timeout=PublicService._FLOORS_CACHE_TTL)
        return category_list

    @staticmethod
    def update_floors_cache():
        """更新首页楼层缓存（后台分类/商品变更时调用）"""
        cache.delete(PublicService._FLOORS_CACHE_KEY)
        logger.info("首页楼层缓存已删除")

    @staticmethod
    def get_index_banners():
        """
        获取首页轮播图

        优先使用后台配置的 Banner，无配置时自动降级为热门推荐商品。

        缓存策略：
        - TTL 1 小时兜底，后台更新时手动触发缓存失效
        - 空 Banner 时降级查商品，空值缓存 60s
        """
        cache_key = PublicService._BANNERS_CACHE_KEY
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        banners = list(BaykeBanners.objects.filter(is_show=True).order_by('-order'))

        if not banners:
            # 降级：推荐商品作为轮播
            goods = list(
                BaykeShopGoods.objects.filter(
                    is_recommend=True, status=BaykeShopGoods.Status.ONLINE
                ).order_by('-sales')[:6]
            )
            if not goods:
                cache.set(cache_key, [], timeout=PublicService._BANNERS_NULL_TTL)
                return []
            # 标记来源，模板据此区分渲染方式
            for g in goods:
                g._is_goods_carousel = True
            cache.set(cache_key, goods, timeout=PublicService._BANNERS_CACHE_TTL)
            return goods

        cache.set(cache_key, banners, timeout=PublicService._BANNERS_CACHE_TTL)
        return banners

    @staticmethod
    def update_banners_cache():
        """后台变更轮播图后调用，主动失效缓存保证一致性"""
        cache.delete(PublicService._BANNERS_CACHE_KEY)
        logger.info(f"轮播图缓存已删除: {PublicService._BANNERS_CACHE_KEY}")


    @staticmethod
    def update_goods_categories_cache():
        """
        更新商品分类缓存（清除导航模板标签缓存，避免导航 stale 最长 5 分钟）
        """
        cache.delete_many([
            "tt:navs:1",   # 导航分类（is_nav=True）
            "tt:navs:0",   # 非导航分类（is_nav=False）
        ])
        logger.info("商品分类缓存已删除")
