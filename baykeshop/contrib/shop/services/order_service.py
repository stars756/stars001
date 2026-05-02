import logging

from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from baykeshop.contrib.shop.models import (
    BaykeShopCarts,
    BaykeShopGoodsImages,
    BaykeShopOrders,
    BaykeShopOrdersGoods,
)

logger = logging.getLogger("baykeshop.contrib.shop")


class OrderServiceError(Exception):
    """订单服务基础异常"""
    pass


class InsufficientStockError(OrderServiceError):
    """库存不足异常"""
    pass


class InvalidQuantityError(OrderServiceError):
    """无效数量异常"""
    pass


class OrderService:
    """订单服务"""

    @staticmethod
    def get_user_orders_queryset(user):
        """
        获取用户订单 QuerySet（用于 API 层）

        Args:
            user: 用户对象

        Returns:
            QuerySet: 用户订单 QuerySet（预取关联数据）
        """
        return BaykeShopOrders.objects.select_related('user').prefetch_related(
            'baykeshopordersgoods_set',
            'baykeshopordersgoods_set__sku',
            'baykeshopordersgoods_set__sku__goods'
        ).filter(user=user)

    @staticmethod
    def validate_stock(goods_data):
        """
        验证订单商品的库存是否充足

        Args:
            goods_data: 商品数据列表，每项含 sku, quantity

        Raises:
            InsufficientStockError: 库存不足时抛出
            InvalidQuantityError: 数量不合法时抛出
        """
        if not goods_data:
            raise InsufficientStockError('请选择商品')
        for item in goods_data:
            if int(item['quantity']) <= 0:
                raise InvalidQuantityError('商品数量必须大于0')
            sku = item.get('sku')
            if sku.stock < int(item['quantity']):
                raise InsufficientStockError('商品库存不足')

    @staticmethod
    def create_order(user, goods_data, source, receiver, phone, address, email):
        """
        创建订单

        Args:
            user: 用户对象
            goods_data: 订单商品列表，每项含 sku, quantity
            source: 订单来源（'carts' 或 'default'）
            receiver, phone, address, email: 收货信息

        Returns:
            BaykeShopOrders: 创建的订单实例
        """
        with transaction.atomic():
            # 计算总价
            pay_price = sum(item['sku'].price * item['quantity'] for item in goods_data)

            # 创建订单
            order = BaykeShopOrders.objects.create(
                user=user,
                pay_price=pay_price,
                receiver=receiver,
                phone=phone,
                address=address,
                email=email,
            )

            # 批量创建订单商品前先预取所有商品图片
            all_goods_ids = set(item['sku'].goods_id for item in goods_data)
            all_images = BaykeShopGoodsImages.objects.filter(goods_id__in=all_goods_ids)
            goods_first_image = {}
            for img in all_images:
                if img.goods_id not in goods_first_image:
                    goods_first_image[img.goods_id] = img.image

            created_objects = BaykeShopOrdersGoods.objects.bulk_create([
                BaykeShopOrdersGoods(orders=order, **OrderService._goods_format(item, goods_first_image))
                for item in goods_data
            ])

            # 扣减库存（直接调用而非通过信号，避免信号耦合）
            for obj in created_objects:
                OrderService.deduct_stock(obj)

            # 清理购物车
            if source == 'carts':
                skus = [item['sku'] for item in goods_data]
                carts = BaykeShopCarts.objects.filter(user=user, sku__in=skus)
                carts.hard_delete()

            # 设置支付 URL
            order.pay_url = reverse('shop:orders-pay', kwargs={'order_sn': order.order_sn})

            logger.info(f"用户 {user.username} 创建订单 {order.order_sn}，金额 {pay_price}")
            return order

    @staticmethod
    def cancel_order(order, user=None, reason=''):
        """
        取消订单（未支付），触发信号回滚库存

        Args:
            order: BaykeShopOrders 实例
            user: 用户对象（可选，用于鉴权）
            reason: 取消原因

        Returns:
            dict: {'success': bool, 'message': str}
        """
        if user and order.user != user:
            return {'success': False, 'message': '无权操作该订单'}
        if order.status == BaykeShopOrders.OrderStatus.UNPAID:
            order.status = BaykeShopOrders.OrderStatus.EXPIRED
            if reason:
                order.cancel_reason = reason
            order.save(update_fields=['status', 'cancel_reason'])
            logger.info(f"用户 {user or 'unknown'} 取消订单 {order.order_sn}, 原因: {reason}")
            return {'success': True, 'message': '取消成功'}
        return {'success': False, 'message': '当前订单状态不支持取消'}

    @staticmethod
    def confirm_receipt(order, user=None):
        """
        确认收货

        Args:
            order: BaykeShopOrders 实例
            user: 用户对象（可选，用于日志）
        """
        order.status = BaykeShopOrders.OrderStatus.SIGNED
        if order.pay_type == BaykeShopOrders.PayType.CASH and not order.pay_time:
            order.pay_time = timezone.now()
        order.save()
        logger.info(f"用户 {user or 'unknown'} 确认收货 {order.order_sn}")

    @staticmethod
    def ship_orders(queryset):
        """
        批量发货 — 单条 SQL 批量更新（PAID→SHIPPED 不触发库存联动，安全）

        Args:
            queryset: BaykeShopOrders QuerySet（仅处理已支付订单）
        """
        to_ship = [o for o in queryset if o.status == BaykeShopOrders.OrderStatus.PAID]
        for o in to_ship:
            o.status = BaykeShopOrders.OrderStatus.SHIPPED
        if to_ship:
            BaykeShopOrders.objects.bulk_update(to_ship, ['status'])
        return len(to_ship)

    # ============================================================
    # 库存/销量管理（替代原 signals.py 中的业务逻辑）
    # ============================================================

    @staticmethod
    def is_virtual_goods(order):
        """判断订单商品是否为虚拟类型（唯一规范来源）"""
        order_goods = order.baykeshopordersgoods_set.first()
        return bool(
            order_goods
            and getattr(order_goods.sku, 'goods', None)
            and order_goods.sku.goods.is_virtual
        )

    @staticmethod
    def get_virtual_content(order):
        """获取虚拟商品内容"""
        if order.status not in {1, 2, 3, 4, 7}:
            return ''
        order_goods = order.baykeshopordersgoods_set.first()
        if order_goods and order_goods.sku:
            return order_goods.sku.email_message
        return ''

    @staticmethod
    def verify_order(order):
        """核销订单（虚拟商品）"""
        if order.status != BaykeShopOrders.OrderStatus.VERIFY:
            return False
        order.status = BaykeShopOrders.OrderStatus.SIGNED
        order.is_verify = True
        order.pay_time = timezone.now()
        order.save(update_fields=['status', 'is_verify', 'pay_time'])
        return True

    @staticmethod
    def deduct_stock(order_good):
        """扣减 SKU 库存（订单商品创建时调用）"""
        sku = order_good.sku
        if sku:
            sku.stock = F("stock") - order_good.quantity
            sku.save(update_fields=['stock'])

    @staticmethod
    def apply_status_transition(order, old_status):
        """
        应用订单状态变更的库存/销量联动逻辑

        信号 pre_save 和 PayService 都委托此方法，
        确保所有路径的库存操作一致。
        """
        from baykeshop.db.orders import BaseOrdersModel

        for order_good in order.baykeshopordersgoods_set.all():
            sku = order_good.sku
            if not sku:
                continue
            qty = order_good.quantity
            s = BaseOrdersModel.OrderStatus

            # UNPAID → EXPIRED：只回滚库存
            if old_status == s.UNPAID and order.status == s.EXPIRED:
                sku.stock = F("stock") + qty
                sku.save(update_fields=['stock'])

            # UNPAID → PAID/SHIPPED/VERIFY：增加销量
            elif old_status == s.UNPAID and order.status in [s.PAID, s.SHIPPED, s.VERIFY]:
                sku.sales = F("sales") + qty
                sku.save(update_fields=['sales'])

            # 已支付 → EXPIRED/REFUNDED：回滚库存 + 减少销量
            elif old_status not in [s.UNPAID, s.EXPIRED] and order.status in [s.EXPIRED, s.REFUNDED]:
                sku.stock = F("stock") + qty
                sku.sales = F("sales") - qty
                sku.save(update_fields=['stock', 'sales'])

            # UNPAID → REFUNDED：只回滚库存
            elif old_status == s.UNPAID and order.status == s.REFUNDED:
                sku.stock = F("stock") + qty
                sku.save(update_fields=['stock'])

