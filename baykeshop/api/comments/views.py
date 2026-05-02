from rest_framework import authentication, mixins, permissions, viewsets

from baykeshop.api.throttles import WriteRateThrottle
from baykeshop.contrib.shop.models import BaykeShopOrdersComment

from .serializers import BaykeShopOrdersCommentSerializer


class BaykeShopOrdersCommentViewSet(mixins.CreateModelMixin,
                                    viewsets.GenericViewSet):
    """订单评论"""
    queryset = BaykeShopOrdersComment.objects.all()
    serializer_class = BaykeShopOrdersCommentSerializer
    authentication_classes = (authentication.SessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)
    # 写操作限流：20次/分钟，防止评论刷屏
    throttle_classes = [WriteRateThrottle]

