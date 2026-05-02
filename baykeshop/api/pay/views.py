from rest_framework import authentication, mixins, permissions, viewsets

from baykeshop.api.throttles import WriteRateThrottle
from baykeshop.contrib.shop.models import BaykeShopOrders

from .serializers import BaykeShopOrdersPaySerializer


class BaykeShopOrdersPayView(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    支付订单
    """
    authentication_classes = (authentication.SessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    # 写操作限流：20次/分钟，防止重复支付请求
    throttle_classes = [WriteRateThrottle]
    # 优化N+1查询：支付时需要订单详情和商品信息
    queryset = BaykeShopOrders.objects.select_related('user').prefetch_related(
        'baykeshopordersgoods_set',
        'baykeshopordersgoods_set__sku',
        'baykeshopordersgoods_set__sku__goods'
    ).all()
    serializer_class = BaykeShopOrdersPaySerializer
    lookup_field = 'order_sn'
    lookup_url_kwarg = 'order_sn'

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)
