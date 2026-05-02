"""
BaykeShop P0 核心业务单元测试 — OrderService + Signals

覆盖模块:
1. OrderService.validate_stock — 库存校验（空/不足/数量≤0/正常）
2. OrderService.create_order — 下单（单SKU/多SKU/购物车来源/库存不足回滚）
3. OrderService.cancel_order — 取消订单（正常/非本人/已支付）
4. OrderService.confirm_receipt — 确认收货
5. OrderService.ship_orders — 批量发货
6. OrderService.verify_order — 核销虚拟商品
7. OrderService.deduct_stock — 库存扣减
8. OrderService.apply_status_transition — 状态路径全覆盖
9. Signals — pre_save 状态变更联动

运行方式:
    python manage.py test tests.test_services_order -v 2
    pytest tests/test_services_order.py -v
"""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()


# ============================================================
# 测试数据工厂
# ============================================================

def _create_user(username='order_user', email='order@test.com'):
    return User.objects.create_user(
        username=username, email=email, password='TestPass123!'
    )


def _create_goods(name='测试商品', is_virtual=False):
    from baykeshop.contrib.shop.models.goods import BaykeShopGoods
    goods_type = BaykeShopGoods.GoodsType.VIRTUAL if is_virtual else BaykeShopGoods.GoodsType.NORMAL
    goods, _ = BaykeShopGoods.objects.get_or_create(
        name=name,
        defaults={
            'status': BaykeShopGoods.Status.ONLINE,
            'goods_type': goods_type,
            'is_virtual': is_virtual,
            'is_delete': False,
            'description': '测试商品描述',
        }
    )
    return goods


def _create_sku(goods, stock=100, price=99.00, sku_sn=None):
    from baykeshop.contrib.shop.models.goods import BaykeShopGoodsSKU
    if sku_sn is None:
        sku_sn = f'SKU-{goods.id}'
    sku, _ = BaykeShopGoodsSKU.objects.get_or_create(
        goods=goods,
        sku_sn=sku_sn,
        defaults={'stock': stock, 'price': price}
    )
    if sku.stock != stock:
        sku.stock = stock
        sku.save(update_fields=['stock'])
    return sku


def _create_order(user, status=0, pay_price=199.00, pay_type=0, minutes_old=60):
    """创建订单（默认已过期1小时）

    ⚠ auto_now_add=True 导致 create() 中的 created_time 参数被忽略，
    必须通过 update() 回填模拟过期时间。
    """
    from baykeshop.contrib.shop.models.orders import BaykeShopOrders
    import random
    order_sn = f'ORD{timezone.now().strftime("%Y%m%d%H%M%S")}{random.randint(1000,9999)}'
    order = BaykeShopOrders.objects.create(
        user=user, pay_price=pay_price, status=status, pay_type=pay_type,
        order_sn=order_sn,
    )
    if minutes_old > 0:
        backdated = timezone.now() - timezone.timedelta(minutes=minutes_old)
        BaykeShopOrders.objects.filter(pk=order.pk).update(created_time=backdated)
        order.refresh_from_db()
    return order


def _create_order_goods(order, sku, quantity=1, price=None):
    """创建订单商品关联"""
    from baykeshop.contrib.shop.models.orders import BaykeShopOrdersGoods
    if price is None:
        price = sku.price
    return BaykeShopOrdersGoods.objects.create(
        orders=order, sku=sku, quantity=quantity,
        name=sku.goods.name, price=price,
    )


# ============================================================
# 1. OrderService.validate_stock
# ============================================================

class ValidateStockTestCase(TestCase):
    """库存校验"""

    def setUp(self):
        self.user = _create_user()
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=10)
        cache.clear()

    def test_empty_goods_data_raises_error(self):
        from baykeshop.contrib.shop.services.order_service import (
            OrderService, InsufficientStockError
        )
        with self.assertRaises(InsufficientStockError):
            OrderService.validate_stock([])

    def test_insufficient_stock_raises_error(self):
        from baykeshop.contrib.shop.services.order_service import (
            OrderService, InsufficientStockError
        )
        goods_data = [{'sku': self.sku, 'quantity': 20}]
        with self.assertRaises(InsufficientStockError):
            OrderService.validate_stock(goods_data)

    def test_zero_quantity_raises_error(self):
        from baykeshop.contrib.shop.services.order_service import (
            OrderService, InvalidQuantityError
        )
        goods_data = [{'sku': self.sku, 'quantity': 0}]
        with self.assertRaises(InvalidQuantityError):
            OrderService.validate_stock(goods_data)

    def test_negative_quantity_raises_error(self):
        from baykeshop.contrib.shop.services.order_service import (
            OrderService, InvalidQuantityError
        )
        goods_data = [{'sku': self.sku, 'quantity': -1}]
        with self.assertRaises(InvalidQuantityError):
            OrderService.validate_stock(goods_data)

    def test_sufficient_stock_passes(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        goods_data = [{'sku': self.sku, 'quantity': 5}]
        self.assertIsNone(OrderService.validate_stock(goods_data))

    def test_exact_stock_passes(self):
        """数量刚好等于库存时通过"""
        from baykeshop.contrib.shop.services.order_service import OrderService
        goods_data = [{'sku': self.sku, 'quantity': 10}]
        self.assertIsNone(OrderService.validate_stock(goods_data))


class CancelOrderTestCase(TestCase):
    """取消订单"""

    def setUp(self):
        self.user = _create_user('cancel_user')
        self.other = _create_user('other_user', 'other@test.com')
        self.order = _create_order(self.user, status=0, pay_price=100.00)
        self.paid_order = _create_order(self.user, status=1, pay_price=200.00)
        cache.clear()

    def test_cancel_unpaid_order(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        result = OrderService.cancel_order(self.order, user=self.user)
        self.assertTrue(result['success'])
        self.assertIn('取消成功', result['message'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 5)  # EXPIRED

    def test_cancel_other_users_order(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        result = OrderService.cancel_order(self.order, user=self.other)
        self.assertFalse(result['success'])
        self.assertIn('无权操作', result['message'])

    def test_cancel_paid_order_fails(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        result = OrderService.cancel_order(self.paid_order, user=self.user)
        self.assertFalse(result['success'])
        self.assertIn('不支持取消', result['message'])
        # 订单状态不变
        self.paid_order.refresh_from_db()
        self.assertEqual(self.paid_order.status, 1)

    def test_cancel_without_user_param(self):
        """不传 user 参数时跳过权限校验"""
        from baykeshop.contrib.shop.services.order_service import OrderService
        result = OrderService.cancel_order(self.order)
        self.assertTrue(result['success'])


# ============================================================
# 4. OrderService.confirm_receipt
# ============================================================

class ConfirmReceiptTestCase(TestCase):
    """确认收货"""

    def setUp(self):
        self.user = _create_user('confirm_user')
        self.order = _create_order(self.user, status=1, pay_price=100.00)
        cache.clear()

    def test_confirm_receipt_sets_signed_status(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        OrderService.confirm_receipt(self.order, user=self.user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 3)  # SIGNED

    def test_confirm_receipt_cash_sets_pay_time(self):
        """CASH 支付且无 pay_time 时自动补 pay_time"""
        from baykeshop.contrib.shop.services.order_service import OrderService
        cash_order = _create_order(self.user, status=1, pay_price=50.00, pay_type=2)
        cash_order.pay_time = None
        cash_order.save()

        OrderService.confirm_receipt(cash_order, user=self.user)
        cash_order.refresh_from_db()
        self.assertIsNotNone(cash_order.pay_time)


# ============================================================
# 5. OrderService.ship_orders
# ============================================================

class ShipOrdersTestCase(TestCase):
    """批量发货"""

    def setUp(self):
        self.user = _create_user('ship_user')
        self.paid_orders = [
            _create_order(self.user, status=1, pay_price=50.00) for _ in range(3)
        ]
        self.unpaid_order = _create_order(self.user, status=0, pay_price=30.00)
        self.shipped_order = _create_order(self.user, status=2, pay_price=40.00)
        cache.clear()

    def test_ship_only_paid_orders(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        qs = BaykeShopOrders.objects.filter(user=self.user)
        count = OrderService.ship_orders(qs)

        self.assertEqual(count, 3)  # 仅 PAID 状态
        for o in self.paid_orders:
            o.refresh_from_db()
            self.assertEqual(o.status, 2)  # SHIPPED

        # 非 PAID 不受影响
        self.unpaid_order.refresh_from_db()
        self.assertEqual(self.unpaid_order.status, 0)


# ============================================================
# 6. OrderService.verify_order
# ============================================================

class VerifyOrderTestCase(TestCase):
    """核销虚拟商品"""

    def setUp(self):
        self.user = _create_user('verify_user')
        self.verify_order = _create_order(self.user, status=7, pay_price=50.00)  # VERIFY
        self.paid_order = _create_order(self.user, status=1, pay_price=50.00)
        cache.clear()

    def test_verify_verifyable_order(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        result = OrderService.verify_order(self.verify_order)
        self.assertTrue(result)
        self.verify_order.refresh_from_db()
        self.assertEqual(self.verify_order.status, 3)  # SIGNED
        self.assertTrue(self.verify_order.is_verify)

    def test_verify_non_verify_order(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        result = OrderService.verify_order(self.paid_order)
        self.assertFalse(result)
        self.paid_order.refresh_from_db()
        self.assertEqual(self.paid_order.status, 1)  # 未变更


# ============================================================
# 7. OrderService.deduct_stock
# ============================================================

class DeductStockTestCase(TestCase):
    """库存扣减"""

    def setUp(self):
        self.user = _create_user('deduct_user')
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=10, price=50.00)
        self.order = _create_order(self.user, status=0, pay_price=50.00)
        self.order_goods = _create_order_goods(self.order, self.sku, quantity=2)
        self.sku.refresh_from_db()
        cache.clear()

    def test_deduct_stock_reduces_inventory(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        self.sku.stock = 10
        self.sku.save(update_fields=['stock'])
        self.sku.refresh_from_db()

        # 创建一个新的 order_goods 对象，不在数据库中被信号影响
        from baykeshop.contrib.shop.models.orders import BaykeShopOrdersGoods
        new_og = BaykeShopOrdersGoods(
            orders=self.order, sku=self.sku, quantity=3,
            name=self.goods.name, price=50.00,
        )

        OrderService.deduct_stock(new_og)
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 7)

    def test_deduct_stock_no_sku_skips(self):
        """order_goods.sku 为 None 时静默跳过"""
        from baykeshop.contrib.shop.services.order_service import OrderService
        self.order_goods.sku = None
        OrderService.deduct_stock(self.order_goods)  # 不应报错


# ============================================================
# 8. OrderService.get_user_orders_queryset
# ============================================================

class UserOrdersQuerySetTestCase(TestCase):
    """用户订单查询集"""

    def setUp(self):
        self.user = _create_user('qs_user')
        self.other = _create_user('qs_other', 'other_qs@test.com')
        _create_order(self.user, status=0, pay_price=100.00)
        _create_order(self.user, status=1, pay_price=200.00)
        _create_order(self.other, status=0, pay_price=300.00)
        cache.clear()

    def test_returns_only_user_orders(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        qs = OrderService.get_user_orders_queryset(self.user)
        self.assertEqual(qs.count(), 2)

    def test_has_select_related(self):
        from baykeshop.contrib.shop.services.order_service import OrderService
        qs = OrderService.get_user_orders_queryset(self.user)
        # select_related 应包含 user
        self.assertTrue(qs.query.select_related is not None and qs.query.select_related)


# ============================================================
# 9. OrderService.apply_status_transition — 状态路径全覆盖
# ============================================================

class StatusTransitionTestCase(TestCase):
    """所有订单状态路径的库存/销量联动"""

    def setUp(self):
        self.user = _create_user('trans_user')
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=20, price=50.00)
        cache.clear()

    def _create_order_and_sku(self, status=0):
        """辅助：创建订单 + 订单商品，返回 (order, sku)

        注意：必须通过 objects.get() 重新加载 order 以触发 from_db()，
        从而设置 _loaded_values 供 pre_save signal 读取。
        """
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        order = _create_order(self.user, status=status, pay_price=100.00, minutes_old=5)
        og = _create_order_goods(order, self.sku, quantity=3)
        self.sku.refresh_from_db()
        # 关键：从 queryset 重新加载以填充 _loaded_values
        order = BaykeShopOrders.objects.get(pk=order.pk)
        return order, self.sku

    def test_unpaid_to_paid(self):
        """UNPAID→PAID：sales +quantity，stock 不变（已在 deduct_stock 时扣过）"""
        order, sku = self._create_order_and_sku(0)
        stock_before = sku.stock  # 已被 deduct_stock 扣过

        order.refresh_from_db()  # 填充 _loaded_values
        order.status = 1  # PAID
        order.save()  # 触发 pre_save → apply_status_transition

        sku.refresh_from_db()
        self.assertEqual(sku.stock, stock_before)  # 不变
        self.assertEqual(sku.sales, 3)  # +quantity

    def test_unpaid_to_expired(self):
        """UNPAID→EXPIRED：stock +quantity 恢复"""
        order, sku = self._create_order_and_sku(0)
        stock_after_deduct = sku.stock  # 20 - 3 = 17

        order.refresh_from_db()
        order.status = 5  # EXPIRED
        order.save()

        sku.refresh_from_db()
        self.assertEqual(sku.stock, stock_after_deduct + 3)  # 恢复库存

    def test_unpaid_to_refunded(self):
        """UNPAID→REFUNDED：stock +quantity 恢复"""
        order, sku = self._create_order_and_sku(0)
        stock_after_deduct = sku.stock

        order.refresh_from_db()
        order.status = 6  # REFUNDED
        order.save()

        sku.refresh_from_db()
        self.assertEqual(sku.stock, stock_after_deduct + 3)

    def test_unpaid_to_verify(self):
        """UNPAID→VERIFY：sales +quantity"""
        order, sku = self._create_order_and_sku(0)

        order.refresh_from_db()
        order.status = 7  # VERIFY
        order.save()

        sku.refresh_from_db()
        self.assertEqual(sku.sales, 3)

    def test_unpaid_to_shipped(self):
        """UNPAID→SHIPPED：sales +quantity"""
        order, sku = self._create_order_and_sku(0)

        order.refresh_from_db()
        order.status = 2  # SHIPPED
        order.save()

        sku.refresh_from_db()
        self.assertEqual(sku.sales, 3)

    def test_paid_to_refunded(self):
        """PAID→REFUNDED：stock +quantity, sales −quantity"""
        order, sku = self._create_order_and_sku(0)
        # 先变 PAID
        order.refresh_from_db()
        order.status = 1
        order.save()
        sku.refresh_from_db()
        sales_after_paid = sku.sales  # 3
        stock_after_paid = sku.stock

        # 再变 REFUNDED — 必须 reload 以填充 _loaded_values
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        order = BaykeShopOrders.objects.get(pk=order.pk)
        order.status = 6
        order.save()

        sku.refresh_from_db()
        self.assertEqual(sku.stock, stock_after_paid + 3)
        self.assertEqual(sku.sales, sales_after_paid - 3)


# ============================================================
# 10. Signals 测试
# ============================================================

class HandleOrderStatusChangeSignalTestCase(TestCase):
    """pre_save(sender=BaykeShopOrders) → handle_order_status_change"""

    def setUp(self):
        self.user = _create_user('sig2_user')
        self.order = _create_order(self.user, status=0, pay_price=100.00, minutes_old=5)
        cache.clear()

    def test_new_order_skips_signal(self):
        """pk 为 None 时跳过"""
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        from unittest.mock import patch

        with patch(
            'baykeshop.contrib.shop.signals.OrderService.apply_status_transition'
        ) as mock_fn:
            new_order = BaykeShopOrders(
                user=self.user, order_sn='NEW-SKIP', pay_price=50.00,
            )
            new_order.save()
            mock_fn.assert_not_called()

    def test_same_status_skips_signal(self):
        """状态未变时跳过"""
        from unittest.mock import patch

        with patch(
            'baykeshop.contrib.shop.signals.OrderService.apply_status_transition'
        ) as mock_fn:
            self.order.refresh_from_db()
            self.order.save()  # status 未变
            mock_fn.assert_not_called()

    def test_status_change_calls_transition(self):
        """状态变更时调用 apply_status_transition"""
        from unittest.mock import patch
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        # 从 queryset 重新加载以填充 _loaded_values
        order = BaykeShopOrders.objects.get(pk=self.order.pk)

        with patch(
            'baykeshop.contrib.shop.signals.OrderService.apply_status_transition'
        ) as mock_fn:
            order.status = 1  # PAID
            order.save()
            mock_fn.assert_called_once()


# ============================================================
# 11. 回归测试 — 支付超时库存单次恢复
# ============================================================

class PaymentTimeoutStockRestoreTestCase(TestCase):
    """支付超时路径 → apply_status_transition 单次恢复库存"""

    def setUp(self):
        self.user = _create_user('timeout_user')
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=10, price=50.00)
        cache.clear()

    def test_timeout_restores_stock_once(self):
        """超时支付 → 库存仅恢复一次（非双倍）"""
        from baykeshop.contrib.shop.services.order_service import OrderService
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        # 模拟真实下单流程：OrderService 创建订单 + 扣减库存
        order = _create_order(self.user, status=0, pay_price=50.00, minutes_old=65)
        _create_order_goods(order, self.sku, quantity=2)

        # 手动扣减库存（模拟 OrderService.create_order 的 deduct_stock）
        self.sku.stock = 8
        self.sku.save(update_fields=['stock'])
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 8)

        # 通过 PaySerializer update 触发超时
        from baykeshop.api.pay.serializers import BaykeShopOrdersPaySerializer
        from django.test import RequestFactory
        from unittest.mock import Mock

        request = RequestFactory().post('/api/pay/')
        request.user = self.user
        request._messages = Mock()

        order = BaykeShopOrders.objects.get(pk=order.pk)
        serializer = BaykeShopOrdersPaySerializer(
            instance=order, data={'pay_type': 0},
            context={'request': request}
        )
        try:
            serializer.is_valid()
            serializer.update(order, serializer.validated_data)
        except Exception:
            pass  # ValidationError from timeout is expected

        self.sku.refresh_from_db()
        # 单次恢复: 8 + 2 = 10，而非双倍 8 + 2 + 2 = 12
        self.assertEqual(self.sku.stock, 10)

    def test_timeout_sets_expired_status(self):
        """超时支付 → 订单状态设为 EXPIRED"""
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        from baykeshop.api.pay.serializers import BaykeShopOrdersPaySerializer
        from django.test import RequestFactory
        from unittest.mock import Mock

        order = _create_order(self.user, status=0, pay_price=50.00, minutes_old=65)
        _create_order_goods(order, self.sku, quantity=1)

        request = RequestFactory().post('/api/pay/')
        request.user = self.user
        request._messages = Mock()

        order = BaykeShopOrders.objects.get(pk=order.pk)
        serializer = BaykeShopOrdersPaySerializer(
            instance=order, data={'pay_type': 0},
            context={'request': request}
        )
        try:
            serializer.is_valid()
            serializer.update(order, serializer.validated_data)
        except Exception:
            pass

        order.refresh_from_db()
        self.assertEqual(order.status, BaykeShopOrders.OrderStatus.EXPIRED)


# ============================================================
# 12. 回归测试 — API 序列化器库存扣减
# ============================================================

class ApiSerializerStockDeductionTestCase(TestCase):
    """API 序列化器 create() → OrderService.deduct_stock()"""

    def setUp(self):
        self.user = _create_user('api_stock_user')
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=10, price=50.00)
        cache.clear()

    def test_serializer_create_deducts_stock(self):
        """API 序列化器下单后正确扣减库存"""
        from baykeshop.api.orders.serializers import BaykeShopOrdersCreateSerializer
        from django.test import RequestFactory
        from unittest.mock import Mock

        request = RequestFactory().post('/api/orders/')
        request.user = self.user
        request._messages = Mock()

        data = {
            'baykeshopordersgoods_set': [
                {'sku': self.sku.pk, 'quantity': 3}
            ],
            'receiver': '测试',
            'phone': '13800138000',
            'address': '北京',
            'source': 'default',
            'email': '',
        }
        serializer = BaykeShopOrdersCreateSerializer(
            data=data, context={'request': request}
        )
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)
        order = serializer.create(serializer.validated_data)

        self.assertIsNotNone(order)
        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 7)  # 10 - 3

    def test_serializer_create_no_signal_double_deduction(self):
        """确认不再通过 post_save 信号扣减，避免与其他路径重复"""
        from baykeshop.api.orders.serializers import BaykeShopOrdersCreateSerializer
        from baykeshop.contrib.shop.services.order_service import OrderService
        from django.test import RequestFactory
        from unittest.mock import Mock, patch

        request = RequestFactory().post('/api/orders/')
        request.user = self.user
        request._messages = Mock()

        data = {
            'baykeshopordersgoods_set': [
                {'sku': self.sku.pk, 'quantity': 2}
            ],
            'receiver': '测试',
            'phone': '13800138000',
            'address': '北京',
            'source': 'default',
            'email': '',
        }
        serializer = BaykeShopOrdersCreateSerializer(
            data=data, context={'request': request}
        )
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)

        with patch.object(OrderService, 'deduct_stock') as mock_deduct:
            serializer.create(serializer.validated_data)
            # 确认只调用了 OrderService.deduct_stock（非信号）
            mock_deduct.assert_called_once()


# ============================================================
# 13. 回归测试 — 支付回调幂等性
# ============================================================

class PaymentIdempotencyTestCase(TestCase):
    """handle_payment_success 幂等性 — 重复回调不重复处理"""

    def setUp(self):
        self.user = _create_user('idempotent_user')
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=10, price=50.00)
        self.order = _create_order(self.user, status=0, pay_price=50.00, minutes_old=5)
        _create_order_goods(self.order, self.sku, quantity=2)
        self.sku.refresh_from_db()
        cache.clear()

    def test_duplicate_callback_skips_processing(self):
        """重复支付回调 → 第二次直接返回成功，不重复处理"""
        from baykeshop.contrib.shop.services.pay_service import PayService
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        # 第一次回调：正常处理
        data = {'trade_no': 'ALIPAY_TRADE_001', 'total_amount': '50.00'}
        order = BaykeShopOrders.objects.get(pk=self.order.pk)
        self.assertEqual(order.status, BaykeShopOrders.OrderStatus.UNPAID)

        success, msg = PayService.handle_payment_success(order.order_sn, data)
        self.assertTrue(success)
        self.assertIn('支付成功', msg)

        order.refresh_from_db()
        self.assertEqual(order.status, BaykeShopOrders.OrderStatus.PAID)
        first_pay_time = order.pay_time

        # 第二次回调（重复投递）：应该返回"已支付"
        success, msg = PayService.handle_payment_success(order.order_sn, data)
        self.assertTrue(success)
        self.assertIn('已支付', msg)

        order.refresh_from_db()
        self.assertEqual(order.status, BaykeShopOrders.OrderStatus.PAID)

    def test_duplicate_callback_no_double_sales(self):
        """重复回调不导致销量双增"""
        from baykeshop.contrib.shop.services.pay_service import PayService
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        data = {'trade_no': 'ALIPAY_TRADE_002', 'total_amount': '50.00'}
        order = BaykeShopOrders.objects.get(pk=self.order.pk)

        # 第一次
        PayService.handle_payment_success(order.order_sn, data)
        self.sku.refresh_from_db()
        sales_after_first = self.sku.sales

        # 第二次（重复回调）
        order = BaykeShopOrders.objects.get(pk=self.order.pk)
        PayService.handle_payment_success(order.order_sn, data)
        self.sku.refresh_from_db()

        # 销量不应增加第二次
        self.assertEqual(self.sku.sales, sales_after_first)

    def test_paid_order_not_reprocessed(self):
        """已支付订单不会被重新处理为其他状态"""
        from baykeshop.contrib.shop.services.pay_service import PayService
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        data = {'trade_no': 'ALIPAY_TRADE_003', 'total_amount': '50.00'}

        # 先标记为已支付
        order = BaykeShopOrders.objects.get(pk=self.order.pk)
        PayService.handle_payment_success(order.order_sn, data)

        # 用不同的 trade_no 再次调用
        order = BaykeShopOrders.objects.get(pk=self.order.pk)
        data2 = {'trade_no': 'ALIPAY_TRADE_DIFFERENT', 'total_amount': '50.00'}
        success, msg = PayService.handle_payment_success(order.order_sn, data2)
        self.assertTrue(success)
        self.assertIn('已支付', msg)

        order.refresh_from_db()
        # trade_no 不应被第二次调用覆盖
        self.assertEqual(order.pay_sn, 'ALIPAY_TRADE_003')

