from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baykeshop.contrib.shop.models import (
    BaykeShopCarts,
    BaykeShopGoodsImages,
    BaykeShopOrders,
    BaykeShopOrdersGoods,
)
from baykeshop.contrib.shop.services.order_service import OrderService


class BaykeShopOrdersGoodsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaykeShopOrdersGoods
        fields = ('sku', 'quantity')


class BaykeShopOrdersCreateSerializer(serializers.ModelSerializer):
    """订单创建序列化器"""
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    baykeshopordersgoods_set = BaykeShopOrdersGoodsSerializer(many=True)
    """ 
        carts: 购物车，这里会查找购物车去清理数据
        default: 直接创建不做任何处理
    """
    source = serializers.ChoiceField(
        choices=('carts', 'default'),
        help_text=_('订单来源'),
        required=False,
        write_only=True,
        default='default'
    )
    pay_url = serializers.CharField(required=False, read_only=True, help_text=_('支付地址'))

    class Meta:
        model = BaykeShopOrders
        fields = (
            'user', 'baykeshopordersgoods_set',
            'receiver', 'phone', 'address', 'source','email',
            'pay_url'
        )

    def validate(self, attrs):
        """验证数据"""
        baykeshopordersgoods_set = attrs.get('baykeshopordersgoods_set')
        if not baykeshopordersgoods_set:
            raise serializers.ValidationError(_('请选择商品'))
        for item in baykeshopordersgoods_set:
            if int(item['quantity']) <= 0:
                raise serializers.ValidationError(_('商品数量必须大于0'))
            sku = item.get('sku')
            if sku.stock < int(item['quantity']):
                raise serializers.ValidationError(_('商品库存不足'))
        return attrs

    def create(self, validated_data):
        """创建订单"""
        source = validated_data.pop('source')
        baykeshopordersgoods_set = validated_data.pop('baykeshopordersgoods_set')
        pay_price = sum([item['sku'].price * item['quantity'] for item in baykeshopordersgoods_set])
        orders = BaykeShopOrders.objects.create(pay_price=pay_price, **validated_data)

        # 批量预取所有商品图片（一次查询，避免 N+1）
        all_goods_ids = set(item['sku'].goods_id for item in baykeshopordersgoods_set)
        all_images = BaykeShopGoodsImages.objects.filter(goods_id__in=all_goods_ids)
        goods_first_image = {}
        for img in all_images:
            if img.goods_id not in goods_first_image:
                goods_first_image[img.goods_id] = img.image

        created_objects = BaykeShopOrdersGoods.objects.bulk_create(
            [BaykeShopOrdersGoods(orders=orders, **self.goods_format(item, goods_first_image))
             for item in baykeshopordersgoods_set]
        )
        # 扣减库存
        for obj in created_objects:
            OrderService.deduct_stock(obj)
        # 清理购物车数据
        if source == 'carts':
            skus = [item['sku'] for item in baykeshopordersgoods_set]
            carts = BaykeShopCarts.objects.filter(user=validated_data['user'], sku__in=skus)
            # 物理删除，无法恢复
            carts.hard_delete()
        orders.pay_url = reverse('shop:orders-pay', kwargs={'order_sn': orders.order_sn})
        messages.success(self.context['request'], _('订单创建成功, 请尽快支付, 否则订单会自动取消'))
        return orders

    def goods_format(self, item, goods_first_image=None):
        """商品格式化（支持预取图片字典，避免 N+1）"""
        sku = item['sku']
        image = ''
        if goods_first_image:
            image = goods_first_image.get(sku.goods_id, '')
        if not image:
            image = self.get_image(sku)
        return {
            'sku': sku,
            'quantity': item['quantity'],
            'price': sku.price,
            'sku_sn': sku.sku_sn,
            'name': sku.goods.name,
            'image': image,
            'specs': sku.specs,
            'detail': sku.goods.detail,
        }

    def get_image(self, sku):
        """获取商品首图（单次查询兜底）"""
        images = BaykeShopGoodsImages.objects.filter(goods=sku.goods)
        if images.exists():
            return images.first().image
        return ''
