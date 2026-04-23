import logging
from django.utils import timezone

from alipay.aop.api.util.SignatureUtils import verify_with_rsa
from baykeshop.contrib.shop.models.orders import BaykeShopOrders
from baykeshop.db.orders import BaseOrdersModel  # OrderStatus 定义在基类上
from baykeshop.contrib.system.models import BaykeDictModel
from baykeshop.db.security import security_logger

logger = logging.getLogger("baykeshop.contrib.shop")


class PayService:
    """支付服务"""

    @staticmethod
    def has_verify_sign(data):
        """
        支付宝支付回调验签

        Args:
            data: 从请求中获得的字典数据，携带 sign和sign_type

        Returns:
            bool: 验签是否通过
        """
        sign = data.pop("sign")
        sign_type = data.pop("sign_type")
        alipay_public_key = BaykeDictModel.get_key_value("ALIPAY_PUBLIC_KEY")
        # 去除sign和sign_type参数之后进行升序排列，拼装请求参数用支付宝公钥进行验签
        message = "&".join(
            [
                f"{k}={v}"
                for k, v in dict(
                    sorted(data.items(), key=lambda d: d[0], reverse=False)
                ).items()
            ]
        )
        flag = verify_with_rsa(
            alipay_public_key, message.encode("UTF-8", "strict"), sign
        )
        return flag

    @staticmethod
    def is_virtual_order(order):
        """判断订单是否为虚拟商品订单"""
        order_goods = order.baykeshopordersgoods_set.first()
        return bool(order_goods and getattr(order_goods.sku, 'goods', None) and order_goods.sku.goods.is_virtual)

    @staticmethod
    def handle_payment_success(order_sn, data):
        """
        处理支付成功逻辑

        Args:
            order_sn: 订单号
            data: 支付宝回调数据字典

        Returns:
            tuple: (bool, str) 是否成功处理，错误消息（如果有）
        """
        try:
            order = BaykeShopOrders.objects.filter(order_sn=order_sn).first()
            if not order:
                return False, "订单不存在"

            order.pay_time = timezone.now()
            order.pay_sn = data.get("trade_no")
            order.status = (
                BaseOrdersModel.OrderStatus.VERIFY  # 虚拟商品 → 待核销
                if PayService.is_virtual_order(order)
                else BaseOrdersModel.OrderStatus.PAID  # 实物商品 → 待发货（PAID）
            )
            order.save()

            # 支付成功安全审计日志
            security_logger.info(
                "PAYMENT_SUCCESS | user=%s | order_sn=%s | trade_no=%s | amount=%s | status=%s",
                order.user.username, order_sn,
                data.get("trade_no"),
                data.get("total_amount", "unknown"),
                order.get_status_display()
            )

            return True, "支付成功"
        except Exception as e:
            logger.exception(f"处理支付成功逻辑失败: {str(e)}")
            return False, f"处理支付成功逻辑失败: {str(e)}"

    @staticmethod
    def get_user_orders_queryset(user):
        """
        获取用户的订单查询集

        Args:
            user: 用户对象

        Returns:
            QuerySet: 用户的订单查询集
        """
        return BaykeShopOrders.objects.filter(user=user)