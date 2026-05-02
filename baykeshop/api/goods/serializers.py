"""商品 API 序列化器"""
from rest_framework import serializers

from baykeshop.contrib.shop.models import BaykeShopCategory, BaykeShopGoods


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = BaykeShopCategory
        fields = ('id', 'name', 'icon', 'is_nav', 'children')

    def get_children(self, obj):
        return CategorySerializer(obj.baykeshopcategory_set.filter(is_nav=True), many=True).data


class GoodsListSerializer(serializers.ModelSerializer):
    """商品列表（不含 SKU 详情）"""
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    image_url = serializers.CharField(read_only=True)
    sales = serializers.IntegerField(read_only=True)

    class Meta:
        model = BaykeShopGoods
        fields = ('id', 'name', 'price', 'image_url', 'sales',
                  'is_recommend', 'is_virtual', 'status')


class GoodsDetailSerializer(serializers.ModelSerializer):
    """商品详情（含 SKU 列表）"""
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    image_url = serializers.CharField(read_only=True)
    sales = serializers.IntegerField(read_only=True)
    skus = serializers.SerializerMethodField()

    class Meta:
        model = BaykeShopGoods
        fields = ('id', 'name', 'price', 'image_url', 'sales', 'description',
                  'detail', 'is_recommend', 'is_virtual', 'status', 'skus')

    def get_skus(self, obj):
        return [
            {'id': s.id, 'sku_sn': s.sku_sn, 'price': str(s.price),
             'line_price': str(s.line_price), 'stock': s.stock, 'specs': s.specs}
            for s in obj.baykeshopgoodssku_set.all()
        ]
