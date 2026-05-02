from rest_framework import viewsets, mixins, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.utils.translation import gettext_lazy as _

from baykeshop.api.throttles import WriteRateThrottle, SensitiveRateThrottle

from baykeshop.api.member.serializers import (
    BaykeShopUserSerializer,
    BaykeShopUserAddressSerializer,
    BaykeShopEmailVerifySerializer,
    BaykeShopSMSVerifySerializer,
    BaykeShopProfileUpdateSerializer,
)
from baykeshop.contrib.member.models import BaykeShopUser, BaykeShopUserAddress
from baykeshop.contrib.member.services.email_verify import MemberVerificationService
from baykeshop.contrib.member.services.sms_verify import MemberSMSAuthService
from baykeshop.contrib.member.services.profile import MemberProfileService
from baykeshop.db.security import get_client_ip



class BaykeShopUserViewSet(mixins.RetrieveModelMixin,
                           mixins.UpdateModelMixin,
                           viewsets.GenericViewSet):
    """用户信息管理"""
    queryset = BaykeShopUser.objects.select_related('user')
    serializer_class = BaykeShopUserSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'user'

    def get_object(self):
        return BaykeShopUser.objects.get(user=self.request.user)


class BaykeShopUserAddressViewSet(mixins.ListModelMixin,
                                   mixins.CreateModelMixin,
                                   mixins.UpdateModelMixin,
                                   mixins.DestroyModelMixin,
                                   viewsets.GenericViewSet):
    """用户地址管理ViewSet"""
    serializer_class = BaykeShopUserAddressSerializer
    permission_classes = [IsAuthenticated]
    # 写操作限流：20次/分钟，防止恶意创建大量垃圾地址
    throttle_classes = [WriteRateThrottle]

    def get_queryset(self):
        return BaykeShopUserAddress.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class BaykeShopEmailVerifyView(views.APIView):
    """邮箱验证API"""
    permission_classes = [IsAuthenticated]
    # 敏感操作限流：10次/分钟，防止邮件轰炸
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        """验证邮箱"""
        serializer = BaykeShopEmailVerifySerializer(
            data=request.data,
            context={'request': request}        
        )
        serializer.is_valid(raise_exception=True)

        result = MemberVerificationService.verify_email(
            serializer.validated_data['token']
        )

        if result['success']:
            return Response({
                'code': 0,
                'msg': result['message']
            })
        return Response({
            'code': 1,
            'msg': result['message']
        }, status=400)


class BaykeShopSMSVerifyView(views.APIView):
    """发送短信验证码API"""
    permission_classes = [IsAuthenticated]
    # 敏感操作限流：10次/分钟，防止短信轰炸
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        """发送短信验证码"""

        serializer = BaykeShopSMSVerifySerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        result = MemberSMSAuthService.send_verification_code(
            serializer.validated_data['user'],
            request,        
            serializer.validated_data.get('operation_type', 'general')          # 默认操作类型为'general'，可以根据需要调整或扩展
        )

        if result['success']:
            return Response({
                'code': 0,
                'msg': result['message']
            })
        return Response({
            'code': 1,
            'msg': result['message']
        }, status=400)


class BaykeShopProfileUpdateView(views.APIView):
    """更新个人资料API"""
    permission_classes = [IsAuthenticated]
    # 敏感操作限流：10次/分钟，防止资料被频繁修改
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        """更新个人资料"""
        serializer = BaykeShopProfileUpdateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        client_ip = get_client_ip(request)
        user = request.user
        errors = {}

        # 敏感字段更新 — 委托 Service 层（内部已含短信验证码校验）
        email = serializer.validated_data.get('email')
        if email and email != user.email:
            result = MemberProfileService.update_email(user, email, client_ip, request)
            if not result['success']:
                errors.update(result.get('error_fields', {}))

        mobile = serializer.validated_data.get('mobile')
        if mobile:
            result = MemberProfileService.update_mobile(user, mobile, client_ip, request)
            if not result['success']:
                errors.update(result.get('error_fields', {}))

        if errors:
            return Response({
                'code': 1,
                'msg': '; '.join(errors.values()),
                'errors': errors,
            }, status=400)

        # 非敏感字段 — 直接更新
        profile = user.baykeshopuser
        for field in ['nickname', 'gender', 'birthday', 'qq', 'wechat', 'description', 'avatar']:
            value = serializer.validated_data.get(field)
            if value is not None:
                setattr(profile, field, value)
        profile.save()

        return Response({
            'code': 0,
            'msg': _('更新成功')
        })

    def get_client_ip(self):
        """获取客户端IP地址"""
        return get_client_ip(self.request)
