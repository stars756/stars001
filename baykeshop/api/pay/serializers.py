from datetime import timedelta
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from django.db.models import F

from baykeshop.contrib.shop.models import BaykeShopOrders
from baykeshop.payment.alipay import TradePagePay


class BaykeShopOrdersPaySerializer(serializers.ModelSerializer):
    """处理支付逻辑
    根据选择的支付方式返回对应的支付地址
    """

    pay_url = serializers.SerializerMethodField()

    class Meta:
        model = BaykeShopOrders
        fields = ("pay_type", "pay_url")

    def validate_pay_type(self, value):
        if value == BaykeShopOrders.PayType.WECHATPAY:
            messages.error(self.context["request"], _("暂不支持微信支付"))
            raise serializers.ValidationError(_("暂不支持微信支付"))
        if self.instance.status != BaykeShopOrders.OrderStatus.UNPAID:
            messages.error(self.context["request"], _("订单状态错误"))
            raise serializers.ValidationError(_("该状态下的订单无法支付, 请联系客服"))
        return value

    def update(self, instance, validated_data):
        if (timezone.now() - instance.created_time) > timedelta(hours=1):
            # 回归库存
            order_goods_list = instance.baykeshopordersgoods_set.all()
            for order_goods in order_goods_list:
                if order_goods.sku:  # 防止sku被删除
                    sku = order_goods.sku
                    sku.stock = F("stock") + order_goods.quantity
                    sku.sales = F("sales") - order_goods.quantity  # 销量也需调整
                    sku.save()

            instance.status = BaykeShopOrders.OrderStatus.EXPIRED
            instance.save()
            messages.error(self.context["request"], _("订单已超时, 请重新下单"))
            raise serializers.ValidationError(_("订单已过期"))

        order_goods = instance.baykeshopordersgoods_set.first()
        # 是否为虚拟商品
        is_virtual = order_goods.sku.goods.is_virtual if order_goods else False
        pay_type = validated_data.get("pay_type")
        if is_virtual and pay_type == BaykeShopOrders.PayType.CASH:
            messages.error(self.context["request"], _("虚拟商品不能使用先用后付"))
            raise serializers.ValidationError(_("虚拟商品不能使用先用后付"))
        if pay_type == BaykeShopOrders.PayType.ALIPAY:
            instance.pay_type = BaykeShopOrders.PayType.ALIPAY
        if pay_type == BaykeShopOrders.PayType.CASH:
            instance.pay_type = BaykeShopOrders.PayType.CASH
            instance.pay_sn = instance.order_sn
            # 先用后付：走正常物流流程，收货时才算付款
            # 不设is_verify，不走待核销，和支付宝一样走 待发货→待收货→待评价
            instance.status = BaykeShopOrders.OrderStatus.PAID
        instance.save()
        return instance

    def get_pay_url(self, instance):
        """获取支付链接"""
        if instance.pay_type == BaykeShopOrders.PayType.CASH:
            messages.success(self.context["request"], _("订单已提交，商家将尽快发货"))
            return reverse(
                "member:orders-detail", kwargs={"order_sn": instance.order_sn}
            )

        # 支付宝回调地址
        request = self.context["request"]
        callback_url = request.build_absolute_uri(reverse("shop:alipay-callback"))
        trade_page_pay = TradePagePay(
            request, instance=instance, return_url=callback_url, notify_url=callback_url
        )
        alipay_url = trade_page_pay.pay()
        return alipay_url
