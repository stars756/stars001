from django.core.cache import cache
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, mixins
from rest_framework.pagination import PageNumberPagination
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from baykeshop.api.throttles import WriteRateThrottle
from baykeshop.contrib.shop.models import BaykeShopCarts
from .serializers import BaykeShopCartsSerializer


class BaykeShopCartsViewSet(mixins.ListModelMixin,
                            mixins.CreateModelMixin,
                            mixins.UpdateModelMixin,
                            mixins.DestroyModelMixin,
                            viewsets.GenericViewSet):
    """购物车模块视图类"""
    pagination_class = PageNumberPagination
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [IsAuthenticated]
    # 写操作限流：20次/分钟，防止购物车被恶意刷
    throttle_classes = [WriteRateThrottle]
    serializer_class = BaykeShopCartsSerializer

    def get_queryset(self):
        return BaykeShopCarts.objects.filter(user=self.request.user)

    def _invalidate_carts_count_cache(self):
        """清除购物车计数缓存，保持前端 header 实时一致"""
        cache.delete(f"tt:carts:{self.request.user.id}")

    def perform_create(self, serializer):
        serializer.save()
        self._invalidate_carts_count_cache()
        messages.success(self.request, _('添加购物车成功'))

    def perform_update(self, serializer):
        serializer.save()
        self._invalidate_carts_count_cache()

    def perform_destroy(self, instance):
        instance.delete()
        self._invalidate_carts_count_cache()
        messages.success(self.request, _('删除购物车成功'))

