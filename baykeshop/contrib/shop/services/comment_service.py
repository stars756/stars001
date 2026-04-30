import logging

from django.db import models
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from baykeshop.contrib.shop.models import BaykeShopOrders, BaykeShopOrdersComment, BaykeShopOrdersGoods

logger = logging.getLogger("baykeshop.contrib.shop")


class CommentService:
    """评论服务（所有公开方法带 1 小时 Redis 缓存）"""

    _CACHE_PREFIX = "comment:spu:"
    _CACHE_TTL = 3600

    @staticmethod
    def _cache_key(spu_id, suffix):
        return f"{CommentService._CACHE_PREFIX}{spu_id}:{suffix}"

    @staticmethod
    def get_spu_queryset(spu):
        """获取某商品（SPU）的公开评论列表（含用户关联预取，避免模板 N+1）"""
        orders = BaykeShopOrdersGoods.objects.filter(
            sku__goods=spu
        ).values_list('orders', flat=True).distinct()
        queryset = BaykeShopOrdersComment.objects.select_related(
            'user__baykeshopuser', 'order'
        ).filter(order_id__in=orders, status=True)
        return queryset.order_by('-created_time')

    @staticmethod
    def get_user_queryset(user):
        """获取用户的评论列表"""
        queryset = BaykeShopOrdersComment.objects.filter(user=user)
        return queryset.order_by('-created_time')

    @staticmethod
    def get_score_avg(spu):
        """获取商品平均评分（带1小时缓存）"""
        cache_key = CommentService._cache_key(spu.id, 'avg')
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        score_avg = CommentService.get_spu_queryset(spu).aggregate(
            score_avg=models.Avg('score')
        ).get('score_avg')
        result = round(score_avg, 1) if score_avg is not None else None
        cache.set(cache_key, result, timeout=CommentService._CACHE_TTL)
        return result

    @staticmethod
    def get_comment_count(spu):
        """获取商品评论总数（带1小时缓存）"""
        cache_key = CommentService._cache_key(spu.id, 'count')
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        count = CommentService.get_spu_queryset(spu).count()
        cache.set(cache_key, count, timeout=CommentService._CACHE_TTL)
        return count

    @staticmethod
    def get_spu_comment_avg_score(spu):
        """获取商品好评率（带1小时缓存）"""
        cache_key = CommentService._cache_key(spu.id, 'rate')
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        gte_3 = CommentService.get_spu_queryset(spu).filter(score__gte=3).count()
        total = CommentService.get_comment_count(spu)
        rate = gte_3 / total if total else 0.98
        result = round(rate * 100, 1)
        cache.set(cache_key, result, timeout=CommentService._CACHE_TTL)
        return result

    @staticmethod
    def get_user_comments(user):
        """获取用户评论 QuerySet"""
        return BaykeShopOrdersComment.objects.filter(order__user=user)

    @staticmethod
    def validate_comment_order(order, user):
        """
        验证订单是否可评论

        Args:
            order: BaykeShopOrders 实例
            user: User 对象

        Raises:
            ValidationError: 订单与用户不匹配、状态不正确或已评论时抛出
        """
        from rest_framework import serializers

        if order.user != user:
            raise serializers.ValidationError(_('订单与当前用户不匹配'))

        if order.status != BaykeShopOrders.OrderStatus.SIGNED:
            raise serializers.ValidationError(_('订单状态不正确，无法评论'))

        if order.is_comment:
            raise serializers.ValidationError(_('订单已评论, 请勿重复评论'))

    @staticmethod
    def create_comment(order, user, content, score):
        """创建评论并更新订单状态"""
        comment = BaykeShopOrdersComment.objects.create(
            order=order, user=order.user, content=content, score=score
        )
        order.is_comment = True
        order.status = BaykeShopOrders.OrderStatus.DONE
        order.save(update_fields=['is_comment', 'status'])

        # 清除该商品（SPU）的评分缓存，避免新评论后评分 stale 最长 1 小时
        order_good = order.baykeshopordersgoods_set.first()
        if order_good and order_good.sku:
            spu_id = order_good.sku.goods_id
            cache.delete_many([
                CommentService._cache_key(spu_id, 'avg'),
                CommentService._cache_key(spu_id, 'count'),
                CommentService._cache_key(spu_id, 'rate'),
            ])

        logger.info(f"用户 {user.username} 评论订单 {order.order_sn}")
        return comment
