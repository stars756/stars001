"""
收藏 API 序列化器
"""
from rest_framework import serializers


class FavoriteToggleSerializer(serializers.Serializer):
    """收藏/取消收藏"""
    goods_id = serializers.IntegerField(required=True, min_value=1)

    def validate_goods_id(self, value):
        from baykeshop.contrib.shop.models.goods import BaykeShopGoods
        if not BaykeShopGoods.objects.filter(id=value).exists():
            raise serializers.ValidationError("商品不存在")
        return value


class FavoriteListSerializer(serializers.Serializer):
    """收藏列表查询参数"""
    page = serializers.IntegerField(required=False, default=1, min_value=1)
