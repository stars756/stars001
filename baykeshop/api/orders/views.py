from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from rest_framework import authentication, mixins, permissions, viewsets

from baykeshop.api.throttles import WriteRateThrottle
from baykeshop.contrib.shop.models import BaykeShopOrders

from .serializers import BaykeShopOrdersCreateSerializer


class BaykeShopOrdersViewSet(mixins.CreateModelMixin,
                             mixins.DestroyModelMixin,
                             viewsets.GenericViewSet):
    """ 创建订单 """
    # 优化N+1查询：预取关联数据，减少数据库查询次数
    queryset = BaykeShopOrders.objects.select_related('user').prefetch_related(
        'baykeshopordersgoods_set',
        'baykeshopordersgoods_set__sku',
        'baykeshopordersgoods_set__sku__goods'
    ).all()
    serializer_class = BaykeShopOrdersCreateSerializer
    authentication_classes = (authentication.SessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    # 写操作限流：20次/分钟，防止恶意下单
    throttle_classes = [WriteRateThrottle]
    lookup_url_kwarg = 'order_sn'
    lookup_field = 'order_sn'

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def perform_destroy(self, instance):
        # 订单删除时同步释放库存（需在serializer或service中实现）
        super().perform_destroy(instance)
        messages.success(self.request, _('订单删除成功'))

