import logging
from django.core.paginator import Paginator
from django.core.cache import cache

from baykeshop.contrib.system.models import Visit
from baykeshop.contrib.shop.models import (
    BaykeShopCategory, BaykeShopGoods,
    BaykeShopOrdersComment, BaykeShopGoodsSKU
)
from baykeshop.contrib.shop.services.cache_utils import CacheableService

logger = logging.getLogger("baykeshop.contrib.shop")


class GoodsService(CacheableService):
    """商品服务 — 继承缓存能力"""

    @staticmethod
    def filter_goods_queryset(queryset, request_params):
        """过滤商品列表"""
        brand_id = request_params.get("brand_id")
        sort = request_params.get("sort", "-created_time")
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        if sort:
            queryset = queryset.order_by(sort)
        return queryset

    @staticmethod
    def get_category_goods(category, request_params):
        """根据分类获取商品"""
        queryset = BaykeShopGoods.objects.filter(category__id=category.id)
        if category.parent is None:
            baykeshopcategory_set = category.baykeshopcategory_set.all()
            queryset = BaykeShopGoods.objects.filter(category__in=baykeshopcategory_set)
            return GoodsService.filter_goods_queryset(queryset, request_params)
        return GoodsService.filter_goods_queryset(queryset, request_params)

    @staticmethod
    def search_goods(queryset, keyword, request_params):
        """搜索商品"""
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)
            return GoodsService.filter_goods_queryset(queryset, request_params)
        return queryset

    @staticmethod
    def create_pv_uv(request, goods):
        """创建PV/UV记录"""
        Visit.objects.create_pv_uv(request, goods)

    @staticmethod
    def get_goods_images(goods):
        """获取商品图片"""
        return goods.baykeshopgoodsimages_set.order_by('order')

    @staticmethod
    def get_recommend_goods(goods, limit=5):
        """获取同类别推荐商品"""
        cates = goods.category.all()
        return list(
            BaykeShopGoods.objects.filter(
                is_recommend=True,
                category__in=cates
            ).exclude(id=goods.id).order_by('-sales')[:limit]
        )

    @staticmethod
    def get_goods_comments(goods, page_number=1, per_page=20):
        """获取商品评论分页"""
        queryset = BaykeShopOrdersComment.get_spu_queryset(goods)
        paginator = Paginator(queryset, per_page)
        return paginator.get_page(page_number)

    @staticmethod
    def get_goods_score_avg(goods):
        """获取商品平均评分"""
        return BaykeShopOrdersComment.get_score_avg(goods)

    @staticmethod
    def get_goods_like_score(goods):
        """获取商品好评率"""
        return BaykeShopOrdersComment.get_spu_comment_avg_score(goods)

    @staticmethod
    def get_goods_comments_count(goods):
        """获取商品评论数"""
        return BaykeShopOrdersComment.get_comment_count(goods)

    # ============================================================
    # 缓存方法 — 使用基类 _cached_get_with_lock 消灭重复代码
    # 原来两个方法各 ~65 行相同逻辑 → 现在每方法 5 行
    # ============================================================

    @classmethod
    def get_goods_detail(cls, sku_id):
        """
        获取商品SKU详情（带缓存三防）
        
        委托给基类 _cached_get_with_lock，无需再手写锁/重试/防雪崩逻辑。
        """
        return cls._cached_get_with_lock(
            cache_prefix="goods_detail",
            pk=sku_id,
            model_class=BaykeShopGoodsSKU,
            base_cache_timeout=1800,  # 30分钟
        )

    @classmethod
    def update_goods_detail_cache(cls, sku_id):
        """更新商品SKU详情缓存（后台调用）"""
        cls.invalidate("goods_detail", sku_id)

    @classmethod
    def get_goods_spu_detail(cls, goods_id, default=None):
        """
        获取商品SPU详情（带缓存三防）
        
        同样委托给基类，与 SKU 版本共享全部缓存策略代码。
        """
        return cls._cached_get_with_lock(
            cache_prefix="goods_spu_detail",
            pk=goods_id,
            model_class=BaykeShopGoods,
            default=default,
        )

    @classmethod
    def update_goods_spu_detail_cache(cls, goods_id):
        """更新商品SPU详情缓存（后台调用）"""
        cls.invalidate("goods_spu_detail", goods_id)
