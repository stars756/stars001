"""
BaykeShop 核心单元测试

覆盖模块:
1. FavoriteService — 收藏/取消收藏/列表/检查
2. FollowService — 关注/取消关注/列表/检查（含 notify_type）
3. PayService — 验签/虚拟商品判断/支付成功处理
4. MemberEmailService — 发送验证邮件/重发
5. MemberVerificationService — Token验证
6. Celery 定时任务 — 自动关单/日统计/Token清理

测试策略：
- 使用 Django TestCase（自动事务回滚，互不干扰）
- Mock 外部依赖：支付宝SDK、Celery任务、邮件发送、Redis缓存
- 每个方法覆盖：正常路径 + 边界条件 + 异常路径

运行方式:
    python manage.py test tests.test_services -v 2
    或: pytest tests/test_services.py -v
"""
import datetime
from unittest.mock import patch, MagicMock, PropertyMock

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache

# ============================================================
# 测试数据工厂（轻量级，不需要 factory_boy）
# ============================================================

User = get_user_model()


def _create_user(username='testuser', email='test@example.com', **kwargs):
    """创建测试用户"""
    user = User.objects.create_user(
        username=username,
        email=email,
        password='TestPass123!',
        **kwargs
    )
    return user


def _create_bayke_user(user):
    """创建会员扩展用户"""
    from baykeshop.contrib.member.models import BaykeShopUser
    bayke_user = BaykeShopUser.objects.create(
        user=user,
        nickname=f'{username}的昵称',
    )
    return bayke_user


def _create_goods(name='测试商品', price=99.00, is_virtual=False, is_show=True):
    """创建测试商品 SPU"""
    from baykeshop.contrib.shop.models.goods import BaykeShopGoodsSPU
    goods, _ = BaykeShopGoodsSPU.objects.get_or_create(
        name=name,
        defaults={
            'price': price,
            'is_virtual': is_virtual,
            'is_show': is_show,
            'is_delete': False,
        }
    )
    return goods


def _create_sku(goods, stock=100, sku_code='SKU001'):
    """创建 SKU"""
    from baykeshop.contrib.shop.models.goods import BaykeShopGoodsSKU
    sku, _ = BaykeShopGoodsSKU.objects.get_or_create(
        goods=goods,
        sku_code=sku_code,
        defaults={'stock': stock}
    )
    return sku


def _create_order(user, status='UNPAID', total_price=199.00, minutes_old=60):
    """创建订单（默认已过期1小时）"""
    from baykeshop.contrib.shop.models.orders import BaykeShopOrders
    created_time = timezone.now() - datetime.timedelta(minutes=minutes_old)
    order = BaykeShopOrders.objects.create(
        user=user,
        total_price=total_price,
        status=status,
        created_time=created_time,
        order_sn=f'TEST{timezone.now().strftime("%Y%m%d%H%M%S")}{order.pk or ""}',
    )
    return order


# ============================================================
# 1. FavoriteService 测试
# ============================================================

class FavoriteServiceTestCase(TestCase):
    """收藏服务单元测试"""

    def setUp(self):
        self.user = _create_user('fav_user', 'fav@test.com')
        self.goods = _create_goods('收藏测试商品', 299.00)
        cache.clear()

    def test_add_favorite_success(self):
        """正常添加收藏"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        result = FavoriteService.add_favorite(self.user, self.goods.id)

        self.assertTrue(result['success'])
        self.assertIn('收藏成功', result['message'])

    def test_add_duplicate_favorite(self):
        """重复收藏应返回失败"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        # 第一次收藏成功
        result1 = FavoriteService.add_favorite(self.user, self.goods.id)
        self.assertTrue(result1['success'])

        # 第二次重复收藏
        result2 = FavoriteService.add_favorite(self.user, self.goods.id)
        self.assertFalse(result2['success'])
        self.assertIn('已经收藏', result2['message'])

    def test_add_nonexistent_goods(self):
        """收藏不存在的商品"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        result = FavoriteService.add_favorite(self.user, 99999)

        self.assertFalse(result['success'])
        self.assertIn('不存在', result['message'])

    def test_remove_favorite_success(self):
        """正常取消收藏"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        # 先收藏
        FavoriteService.add_favorite(self.user, self.goods.id)

        # 再取消
        result = FavoriteService.remove_favorite(self.user, self.goods.id)
        self.assertTrue(result['success'])
        self.assertIn('取消收藏', result['message'])

    def test_remove_nonexistent_favorite(self):
        """取消未收藏的商品"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        result = FavoriteService.remove_favorite(self.user, self.goods.id)
        self.assertFalse(result['success'])
        self.assertIn('未收藏', result['message'])

    def test_is_favorited_true(self):
        """已收藏时返回 True"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        FavoriteService.add_favorite(self.user, self.goods.id)
        self.assertTrue(FavoriteService.is_favorited(self.user, self.goods.id))

    def test_is_favorited_false(self):
        """未收藏时返回 False"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        self.assertFalse(FavoriteService.is_favorited(self.user, self.goods.id))

    def test_get_favorites_count_empty(self):
        """无收藏时计数为0"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        count = FavoriteService.get_favorites_count(self.user)
        self.assertEqual(count, 0)

    def test_get_favorites_count_after_add(self):
        """有收藏后计数正确"""
        from baykeshop.contrib.shop.services.favorite_service import FavoriteService

        FavoriteService.add_favorite(self.user, self.goods.id)
        count = FavoriteService.get_favorites_count(self.user)
        self.assertEqual(count, 1)


# ============================================================
# 2. FollowService 测试（含 notify_type 过滤）
# ============================================================

class FollowServiceTestCase(TestCase):
    """关注服务单元测试"""

    def setUp(self):
        self.user = _create_user('follow_user', 'follow@test.com')
        self.goods = _create_goods('关注测试商品', 399.00)
        cache.clear()

    def test_add_follow_default_type(self):
        """默认关注类型为 arrival（到货通知）"""
        from baykeshop.contrib.shop.services.follow_service import FollowService

        result = FollowService.add_follow(self.user, self.goods.id)
        self.assertTrue(result['success'])

    def test_add_follow_arrival_type(self):
        """到货通知关注"""
        from baykeshop.contrib.shop.services.follow_service import FollowService

        result = FollowService.add_follow(self.user, self.goods.id, notify_type='arrival')
        self.assertTrue(result['success'])

    def test_is_followed_with_type_filtering(self):
        """按类型过滤的关注状态检查"""
        from baykeshop.contrib.shop.services.follow_service import FollowService

        FollowService.add_follow(self.user, self.goods.id, notify_type='arrival')

        self.assertTrue(FollowService.is_followed(self.user, self.goods.id, 'arrival'))
        # 没有降价关注，应为 False
        self.assertFalse(FollowService.is_followed(self.user, self.goods.id, 'price_drop'))

    def test_remove_follow_specific_type(self):
        """取消特定类型的关注"""
        from baykeshop.contrib.shop.services.follow_service import FollowService

        FollowService.add_follow(self.user, self.goods.id, notify_type='arrival')
        FollowService.add_follow(self.user, self.goods.id, notify_type='price_drop')

        # 只取消到货关注
        result = FollowService.remove_follow(self.user, self.goods.id, notify_type='arrival')
        self.assertTrue(result['success'])

        # 到货关注已取消，降价关注仍在
        self.assertFalse(FollowService.is_followed(self.user, self.goods.id, 'arrival'))
        self.assertTrue(FollowService.is_followed(self.user, self.goods.id, 'price_drop'))

    def test_get_follows_count_by_type(self):
        """按类型过滤的关注计数"""
        from baykeshop.contrib.shop.services.follow_service import FollowService

        FollowService.add_follow(self.user, self.goods.id, notify_type='arrival')

        arrival_count = FollowService.get_follows_count(self.user, notify_type='arrival')
        all_count = FollowService.get_follows_count(self.user)  # 不过滤

        self.assertEqual(arrival_count, 1)
        self.assertEqual(all_count, 1)


# ============================================================
# 3. PayService 测试
# ============================================================

class PayServiceTestCase(TestCase):
    """支付服务单元测试"""

    def setUp(self):
        self.user = _create_user('pay_user', 'pay@test.com')
        self.goods = _create_goods('支付测试商品', 599.00, is_virtual=False)
        self.virtual_goods = _create_goods('虚拟商品', 9.99, is_virtual=True)
        cache.clear()

    @patch('baykeshop.contrib.shop.services.pay_service.BaykeDictModel')
    @patch('baykeshop.contrib.shop.services.pay_service.verify_with_rsa')
    def test_verify_sign_success(self, mock_verify, mock_dict_model):
        """验签成功"""
        from baykeshop.contrib.shop.services.pay_service import PayService

        mock_dict_model.get_key_value.return_value = 'fake_public_key'
        mock_verify.return_value = True

        data = {
            'out_trade_no': 'TEST123',
            'trade_no': 'ALI20240101',
            'total_amount': '599.00',
            'sign': 'fakesign',
            'sign_type': 'RSA2',
        }

        self.assertTrue(PayService.has_verify_sign(data))

    @patch('baykeshop.contrib.shop.services.pay_service.BaykeDictModel')
    @patch('baykeshop.contrib.shop.services.pay_service.verify_with_rsa')
    def test_verify_sign_fail(self, mock_verify, mock_dict_model):
        """验签失败"""
        from baykeshop.contrib.shop.services.pay_service import PayService

        mock_dict_model.get_key_value.return_value = 'fake_public_key'
        mock_verify.return_value = False

        data = {
            'out_trade_no': 'TEST123',
            'sign': 'fakesign',
            'sign_type': 'RSA2',
        }

        self.assertFalse(PayService.has_verify_sign(data))

    def test_is_virtual_order_true(self):
        """虚拟商品订单判断为 True"""
        from baykeshop.contrib.shop.services.pay_service import PayService

        virtual_order = _create_order(self.user, 'UNPAID', 9.99)
        sku = _create_sku(self.virtual_goods)
        # 关联虚拟商品到订单
        from baykeshop.contrib.shop.models.orders import BaykeShopOrdersGoods
        BaykeShopOrdersGoods.objects.create(
            order=virtual_order,
            sku=sku,
            goods_num=1,
            price=9.99,
        )

        self.assertTrue(PayService.is_virtual_order(virtual_order))

    def test_is_virtual_order_false(self):
        """实物商品订单判断为 False"""
        from baykeshop.contrib.shop.services.pay_service import PayService

        normal_order = _create_order(self.user, 'UNPAID', 599.00)
        sku = _create_sku(self.goods)
        from baykeshop.contrib.shop.models.orders import BaykeShopOrdersGoods
        BaykeShopOrdersGoods.objects.create(
            order=normal_order,
            sku=sku,
            goods_num=1,
            price=599.00,
        )

        self.assertFalse(PayService.is_virtual_order(normal_order))

    @patch('baykeshop.db.security.security_logger')
    def test_handle_payment_success_normal(self, mock_security_logger):
        """处理支付成功——实物商品变为 PAID 状态"""
        from baykeshop.contrib.shop.services.pay_service import PayService
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders

        order = _create_order(self.user, 'UNPAID', 599.00)
        sku = _create_sku(self.goods)
        from baykeshop.contrib.shop.models.orders import BaykeShopOrdersGoods
        BaykeShopOrdersGoods.objects.create(
            order=order, sku=sku, goods_num=1, price=599.00,
        )

        callback_data = {
            'trade_no': 'ALI_TEST_12345',
            'total_amount': '599.00',
        }

        success, msg = PayService.handle_payment_success(order.order_sn, callback_data)

        self.assertTrue(success)
        order.refresh_from_db()
        self.assertEqual(order.status, BaykeShopOrders.OrderStatus.PAID)
        self.assertIsNotNone(order.pay_time)
        self.assertEqual(order.pay_sn, 'ALI_TEST_12345')
        mock_security_logger.info.assert_called_once()  # 安全日志被调用

    def test_handle_payment_nonexistent_order(self):
        """处理不存在的订单号"""
        from baykeshop.contrib.shop.services.pay_service import PayService

        success, msg = PayService.handle_payment_success('NONEXISTENT', {})

        self.assertFalse(success)
        self.assertIn('不存在', msg)

    def test_get_user_orders_queryset(self):
        """获取用户订单查询集"""
        from baykeshop.contrib.shop.services.pay_service import PayService

        _create_order(self.user, 'PAID', 100.00)
        _create_order(self.user, 'UNPAID', 200.00)

        qs = PayService.get_user_orders_queryset(self.user)
        self.assertEqual(qs.count(), 2)


# ============================================================
# 4. MemberEmailService 测试
# ============================================================

class MemberEmailServiceTestCase(TestCase):
    """邮箱验证服务单元测试"""

    def setUp(self):
        self.user = _create_user('email_user', 'email@test.com')
        self.bayke_user = _create_bayke_user(self.user)
        cache.clear()

    @patch('baykeshop.contrib.member.services.email_verify.send_verification_email_to_user')
    @patch('baykeshop.conf.bayke_settings')
    def test_send_verification_email_success(self, mock_settings, mock_send_email):
        """发送验证邮件成功"""
        from baykeshop.contrib.member.services.email_verify import MemberEmailService

        mock_settings.CACHE_PREFIX_EMAIL_VERIFY_LIMIT = 'email_verify_limit'
        mock_settings.EMAIL_VERIFY_COOLDOWN_SECONDS = 300
        mock_settings.EMAIL_RESEND_COOLDOWN_SECONDS = 300
        mock_send_email.return_value = {'success': True}

        result = MemberEmailService.send_verification_email(
            self.user, self.bayke_user
        )

        self.assertTrue(result['success'])
        mock_send_email.assert_called_once()

    def test_resend_already_verified(self):
        """重发——已验证过的邮箱直接返回成功"""
        from baykeshop.contrib.member.services.email_verify import MemberEmailService

        self.bayke_user.is_email_verified = True
        self.bayke_user.save()

        result = MemberEmailService.resend_verification_email(self.user)

        self.assertTrue(result['success'])
        self.assertIn('已经验证过', result['message'])

    @patch('baykeshop.contrib.member.tasks.send_email_task')
    def test_resend_rate_limited(self, mock_send_task):
        """重发——频率限制拦截"""
        from baykeshop.contrib.member.services.email_verify import MemberEmailService
        from baykeshop.conf import bayke_settings

        resend_key = f"{bayke_settings.CACHE_PREFIX_EMAIL_RESEND_LIMIT}:{self.user.id}"
        cache.set(resend_key, 1, timeout=300)

        result = MemberEmailService.resend_verification_email(self.user)

        self.assertFalse(result['success'])
        self.assertIn('频繁', result['message'])
        mock_send_task.delay.assert_not_called()  # 不应调用异步发送


# ============================================================
# 5. MemberVerificationService 测试
# ============================================================

class MemberVerificationServiceTestCase(TestCase):
    """Token 验证服务单元测试"""

    def setUp(self):
        self.user = _create_user('verify_user', 'verify@test.com')
        self.bayke_user = _create_bayke_user(self.user)
        cache.clear()

    def test_verify_invalid_token(self):
        """无效 Token 返回失败"""
        from baykeshop.contrib.member.services.email_verify import MemberVerificationService

        result = MemberVerificationService.verify_email('INVALID_TOKEN_12345')

        self.assertFalse(result['success'])
        self.assertIn('无效或已过期', result['message'])

    def test_verify_already_verified(self):
        """已验证用户重复验证返回提示"""
        from baykeshop.contrib.member.services.email_verify import MemberVerificationService
        from baykeshop.db.security import generate_verification_token

        self.bayke_user.is_email_verified = True
        self.bayke_user.email_verification_token = generate_verification_token()
        self.bayke_user.save()

        result = MemberVerificationService.verify_email(
            self.bayke_user.email_verification_token
        )

        self.assertFalse(result['success'])
        self.assertIn('已经验证过', result['message'])

    def test_verify_expired_token(self):
        """过期 Token 验证失败"""
        from baykeshop.contrib.member.services.email_verify import MemberVerificationService
        from baykeshop.db.security import generate_verification_token

        token = generate_verification_token()
        self.bayke_user.email_verification_token = token
        # 设为一个很早的时间，模拟过期
        self.bayke_user.email_verify_at = timezone.now() - datetime.timedelta(days=7)
        self.bayke_user.save()
        self.bayke_user.refresh_from_db()

        result = MemberVerificationService.verify_email(token)

        self.assertFalse(result['success'])
        self.assertIn('过期', result['message'])


# ============================================================
# 6. Celery 周期性任务测试
# ============================================================

class CeleryPeriodicTasksTestCase(TestCase):
    """Celery 定时任务单元测试"""

    def setUp(self):
        self.user = _create_user('task_user', 'task@test.com')
        cache.clear()

    def test_auto_close_expired_orders(self):
        """自动关闭超时未支付订单"""
        from baykeshop.contrib.shop.tasks import auto_close_expired_orders

        # 创建一个超时的待支付订单
        expired_order = _create_order(self.user, 'UNPAID', 100.00, minutes_old=60)

        with override_settings(ORDER_EXPIRE_MINUTES=30):
            task = auto_close_expired_requests.Mock()
            task.request = MagicMock()
            result = auto_close_expired_orders(task)

        self.assertEqual(result['closed'], 1)
        expired_order.refresh_from_db()
        self.assertNotEqual(expired_order.status, 'UNPAID')  # 应已被关闭

    def test_auto_close_no_expired_orders(self):
        """无超时订单时不操作"""
        from baykeshop.contrib.shop.tasks import auto_close_expired_orders

        # 创建一个刚下的订单，还没过期
        new_order = _create_order(self.user, 'UNPAID', 200.00, minutes_old=10)

        with override_settings(ORDER_EXPIRE_MINUTES=30):
            task = auto_close_expired_requests.Mock()
            result = auto_close_expired_orders(task)

        self.assertEqual(result['closed'], 0)
        new_order.refresh_from_db()
        self.assertEqual(new_order.status, 'UNPAID')  # 未受影响

    def test_cleanup_expired_tokens(self):
        """清理过期 Token"""
        from baykeshop.contrib.member.models import BaykeShopUser
        from baykeshop.contrib.shop.tasks import cleanup_expired_tokens
        from baykeshop.db.security import generate_verification_token

        # 创建一个有过期 Token 的用户
        bayke_user = _create_bayke_user(self.user)
        bayke_user.email_verification_token = generate_verification_token()
        bayke_user.email_verify_at = timezone.now() - datetime.timedelta(days=7)
        bayke_user.is_email_verified = False
        bayke_user.save()

        task = cleanup_expired_tokens.Mock()
        result = cleanup_expired_tokens(task)

        self.assertEqual(result['cleared'], 1)
        bayke_user.refresh_from_db()
        self.assertIsNone(bayke_user.email_verification_token)  # Token 已清除

    def test_cache_warmup_homepage(self):
        """首页缓存预热"""
        from baykeshop.contrib.shop.tasks import cache_warmup_homepage

        task = cache_warmup_homepage.Mock()
        result = cache_warmup_homepage(task)

        self.assertEqual(result['status'], 'ok')
        self.assertGreaterEqual(len(result['warmed_keys']), 1)
        # 验证缓存确实写入
        self.assertIsNotNone(cache.get('banners:active'))


# ============================================================
# 7. API 限流测试
# ============================================================

class APIThrottleTestCase(TestCase):
    """API 限流防刷单元测试"""

    def setUp(self):
        self.client = self.client_class()  # Django TestClient
        self.user = _create_user('throttle_user', 'throttle@test.com')
        self.client.force_login(self.user)
        cache.clear()

    def test_sensitive_throttle_on_sms_endpoint(self):
        """SMS 接口使用敏感限流类"""
        from baykeshop.api.throttles import SensitiveRateThrottle
        from baykeshop.api.member.views import BaykeShopSMSVerifyView

        view = BaykeShopSMSVerifyView()
        throttle_classes = getattr(view, 'throttle_classes', [])
        self.assertIn(SensitiveRateThrottle, throttle_classes)

    def test_upload_throttle_on_upload_endpoint(self):
        """上传接口使用上传限流类"""
        from baykeshop.api.throttles import UploadRateThrottle
        from baykeshop.api.upload.views import UploadImageView

        view = UploadImageView()
        throttle_classes = getattr(view, 'throttle_classes', [])
        self.assertIn(UploadRateThrottle, throttle_classes)

    def test_write_throttle_on_cart_endpoint(self):
        """购物车接口使用写操作限流"""
        from baykeshop.api.throttles import WriteRateThrottle
        from baykeshop.api.carts.views import BaykeShopCartsViewSet

        view = BaykeShopCartsViewSet()
        throttle_classes = getattr(view, 'throttle_classes', [])
        self.assertIn(WriteRateThrottle, throttle_classes)

    def test_all_views_have_throttle_config(self):
        """所有视图都有限流配置（回归保护）"""
        views_to_check = [
            ('api.carts.views', 'BaykeShopCartsViewSet'),
            ('api.comments.views', 'BaykeShopOrdersCommentViewSet'),
            ('api.orders.views', 'BaykeShopOrdersViewSet'),
            ('api.pay.views', 'BaykeShopOrdersPayView'),
            ('api.upload.views', 'UploadImageView'),
        ]

        for module_name, class_name in views_to_check:
            module = __import__(module_name, fromlist=[class_name])
            view_cls = getattr(module, class_name)
            self.assertIsNotNone(
                getattr(view_cls, 'throttle_classes', None),
                f"{class_name} 缺少 throttle_classes 配置"
            )
