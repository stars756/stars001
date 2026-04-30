"""
BaykeShop API 集成测试 — DRF APIClient 端到端测试

运行: pytest tests/test_api_integration.py -v
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

User = get_user_model()


def _create_user(username='api_user', email='api@test.com'):
    return User.objects.create_user(
        username=username, email=email, password='TestPass123!'
    )


def _create_goods(name='API测试商品'):
    from baykeshop.contrib.shop.models.goods import BaykeShopGoods
    goods, _ = BaykeShopGoods.objects.get_or_create(
        name=name,
        defaults={'status': 1, 'goods_type': 1, 'is_delete': False}
    )
    return goods


def _create_sku(goods, stock=100, price=99.00):
    from baykeshop.contrib.shop.models.goods import BaykeShopGoodsSKU
    sku, _ = BaykeShopGoodsSKU.objects.get_or_create(
        goods=goods, sku_sn=f'SKU-API-{goods.id}',
        defaults={'stock': stock, 'price': price}
    )
    return sku


class CartApiTestCase(TestCase):
    """购物车 API /api/carts/"""

    def setUp(self):
        self.api = APIClient()
        self.user = _create_user('cart_api_user')
        self.api.force_login(self.user)
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=50, price=99.00)
        cache.clear()

    def test_add_to_cart(self):
        """POST /api/carts/ → 201"""
        resp = self.api.post('/api/carts/', {
            'sku': self.sku.pk, 'quantity': 2
        }, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_list_cart(self):
        """GET /api/carts/ → 返回购物车列表"""
        self.api.post('/api/carts/', {
            'sku': self.sku.pk, 'quantity': 3
        }, format='json')

        resp = self.api.get('/api/carts/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('count', data)
        self.assertGreaterEqual(data['count'], 1)

    def test_cart_requires_auth(self):
        """未认证 → 403"""
        self.api.logout()
        resp = self.api.get('/api/carts/')
        self.assertEqual(resp.status_code, 403)


class OrderApiTestCase(TestCase):
    """订单 API /api/orders/"""

    def setUp(self):
        self.api = APIClient()
        self.user = _create_user('order_api_user')
        self.api.force_login(self.user)
        self.goods = _create_goods()
        self.sku = _create_sku(self.goods, stock=10, price=99.00)
        cache.clear()

    def test_create_order_deducts_stock(self):
        """POST /api/orders/ → 201 并扣减库存"""
        resp = self.api.post('/api/orders/', {
            'baykeshopordersgoods_set': [
                {'sku': self.sku.pk, 'quantity': 2}
            ],
            'receiver': '张三',
            'phone': '13800138000',
            'address': '北京市朝阳区',
            'source': 'default',
            'email': '',
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn('pay_url', data)

        self.sku.refresh_from_db()
        self.assertEqual(self.sku.stock, 8)  # 10 - 2

    def test_create_order_insufficient_stock(self):
        """库存不足 → 400"""
        resp = self.api.post('/api/orders/', {
            'baykeshopordersgoods_set': [
                {'sku': self.sku.pk, 'quantity': 100}
            ],
            'receiver': '李四',
            'phone': '13900139000',
            'address': '上海市浦东新区',
            'email': '',
        }, format='json')

        self.assertEqual(resp.status_code, 400)

    def test_order_requires_auth(self):
        """未认证 → 403"""
        self.api.logout()
        resp = self.api.post('/api/orders/', {
            'baykeshopordersgoods_set': [{'sku': self.sku.pk, 'quantity': 1}],
            'receiver': '王五', 'phone': '13700137000',
            'address': '广州', 'email': '',
        }, format='json')
        self.assertEqual(resp.status_code, 403)


class UserApiTestCase(TestCase):
    """用户 API /api/user/"""

    def setUp(self):
        self.api = APIClient()
        self.user = _create_user('user_api_user')
        from baykeshop.contrib.member.models import BaykeShopUser
        BaykeShopUser.objects.get_or_create(user=self.user, defaults={'nickname': 'test'})
        self.api.force_login(self.user)
        cache.clear()

    def test_retrieve_current_user(self):
        """GET /api/user/{pk}/ → 返回用户信息"""
        resp = self.api.get(f'/api/user/{self.user.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_user_requires_auth(self):
        """未认证 → 403"""
        self.api.logout()
        resp = self.api.get(f'/api/user/{self.user.pk}/')
        self.assertEqual(resp.status_code, 403)


class AddressApiTestCase(TestCase):
    """收货地址 API /api/addresses/"""

    def setUp(self):
        self.api = APIClient()
        self.user = _create_user('addr_api_user')
        self.api.force_login(self.user)
        cache.clear()

    def test_create_address(self):
        """POST /api/addresses/ → 201"""
        resp = self.api.post('/api/addresses/', {
            'name': '收货人',
            'phone': '13800138000',
            'province': '北京',
            'city': '北京市',
            'district': '朝阳区',
            'address': '某某路 100 号',
        }, format='json')

        self.assertEqual(resp.status_code, 201)

    def test_list_addresses(self):
        """GET /api/addresses/ → 返回列表"""
        self.api.post('/api/addresses/', {
            'name': '收货人',
            'phone': '13800138000',
            'province': '北京', 'city': '北京市',
            'district': '朝阳区', 'address': '某某路 100 号',
        }, format='json')

        resp = self.api.get('/api/addresses/')
        self.assertEqual(resp.status_code, 200)

    def test_address_requires_auth(self):
        """未认证 → 403"""
        self.api.logout()
        resp = self.api.get('/api/addresses/')
        self.assertEqual(resp.status_code, 403)
