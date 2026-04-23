from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin
from django.urls import reverse

from baykeshop.contrib.member.models import BaykeShopUser, SecurityLog
from baykeshop.contrib.member.security import get_client_ip, record_security_log


class IPVerificationMiddleware(MiddlewareMixin):
    """
    IP验证中间件
    检查已登录用户的IP是否可信，不可信则强制登出
    """

    def process_request(self, request):
        """
        处理请求，检查IP可信度
        """
        # 跳过非认证请求和特定URL
        if not request.user.is_authenticated:
            return None

        # 跳过特定的URL路径（登出、登录、IP验证）
        if request.path in [reverse('member:logout'), reverse('member:login'), reverse('member:verify_ip')]:
            return None

        try:
            # 获取用户扩展信息
            bayke_user = BaykeShopUser.objects.get(user=request.user)

            # 获取客户端IP
            client_ip = get_client_ip(request)

            # 验证IP可信度
            is_trusted, message = bayke_user.is_ip_trusted(client_ip)

            if not is_trusted:
                # 记录安全日志
                record_security_log(
                    user=request.user,
                    ip_address=client_ip,
                    action_type=SecurityLog.ActionTypes.IP_UNTRUSTED_ACCESS,
                    action_detail=f"用户从不可信IP {client_ip} 访问，强制登出",
                    status=SecurityLog.StatusChoices.FAILED
                )

                # 清除会话
                request.session.flush()
                request.user = None

                # 添加错误消息
                messages.error(request, "检测到异常IP访问，系统已自动登出您的账号以保障安全。")

                # 重定向到登录页面
                return redirect(reverse('member:login'))

        except BaykeShopUser.DoesNotExist:
            # 如果用户没有扩展信息，跳过检查
            return None

        return None


def ip_verification_required(view_func):
    """
    IP验证装饰器
    用于视图函数，确保用户IP可信
    """
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('member:login'))

        try:
            bayke_user = BaykeShopUser.objects.get(user=request.user)
            client_ip = get_client_ip(request)

            if not bayke_user.is_ip_trusted(client_ip):
                messages.error(request, "检测到异常IP访问，请重新登录。")
                return redirect(reverse('member:login'))

        except BaykeShopUser.DoesNotExist:
            messages.error(request, "用户信息异常，请重新登录。")
            return redirect(reverse('member:login'))

        return view_func(request, *args, **kwargs)

    return wrapped_view