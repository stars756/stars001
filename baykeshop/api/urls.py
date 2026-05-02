from django.urls import path
from rest_framework import routers

from baykeshop.api.carts import views as carts_views
from baykeshop.api.comments import views as comments_views
from baykeshop.api.favorites import views as favorites_views
from baykeshop.api.member import views as member_views
from baykeshop.api.orders import views as orders_views
from baykeshop.api.pay import views as pay_views
from baykeshop.api.upload import views as upload_views

router = routers.DefaultRouter()
# 路由命名空间
app_name = 'baykeshop_api'
# 购物车
router.register('carts', carts_views.BaykeShopCartsViewSet, basename='carts')
# 支付订单
router.register('pay', pay_views.BaykeShopOrdersPayView, basename='pay')
# 订单评论
router.register('comments', comments_views.BaykeShopOrdersCommentViewSet, basename='comments')
# 创建订单和删除订单
router.register('orders', orders_views.BaykeShopOrdersViewSet, basename='orders')
# 用户管理
router.register('user', member_views.BaykeShopUserViewSet, basename='user')
# 用户地址管理
router.register('addresses', member_views.BaykeShopUserAddressViewSet, basename='addresses')

urlpatterns = [
    path('upload/image/', upload_views.UploadImageView.as_view(), name='upload-image'),
    # 邮箱验证
    path('verify-email/', member_views.BaykeShopEmailVerifyView.as_view(), name='verify-email'),
    # 短信验证
    path('send-sms/', member_views.BaykeShopSMSVerifyView.as_view(), name='send-sms'),
    # 个人资料更新
    path('profile/update/', member_views.BaykeShopProfileUpdateView.as_view(), name='profile-update'),
    # 收藏切换
    path('favorites/toggle/', favorites_views.FavoriteToggleView.as_view(), name='favorites-toggle'),
    # 收藏列表
    path('favorites/', favorites_views.FavoriteListView.as_view(), name='favorites-list'),
    *router.urls
]
