from django.contrib.auth import get_user_model
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView
)
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.views.generic import FormView, View
from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy
from django.contrib.auth import login as auth_login
from django.shortcuts import redirect

from django.core.cache import cache

from baykeshop.conf import bayke_settings

from baykeshop.db.security import get_client_ip, add_trusted_ip
from baykeshop.contrib.member.forms import LoginForm, RegisterForm, BaykePasswordResetForm, BaykePasswordResetConfirmForm
from baykeshop.contrib.member.models import BaykeShopUser, SecurityLog
from baykeshop.contrib.member.services.ip_verify import (
    MemberAuthService,
)
from baykeshop.contrib.member.services.email_verify import (
    MemberEmailService,
    MemberVerificationService,
)
from baykeshop.contrib.member.services.sms_verify import MemberSMSAuthService
from baykeshop.contrib.common.mixins import BaykeLoginRequiredMixin

User = get_user_model()


class BaykeShopUserLoginView(SuccessMessageMixin, LoginView):
    """登录页面"""

    template_name = "baykeshop/member/login.html"
    redirect_field_name = "next"
    next_page = reverse_lazy("shop:list")
    form_class = LoginForm
    extra_context = {
        "title": _("登录"),
    }
    success_message = _("登录成功")

    def form_valid(self, form):
        """登录成功，调用业务服务层处理验证逻辑"""
        user = form.get_user()
        auth_login(self.request, user)

        result = MemberAuthService.authenticate_login(user, self.request)

        if not result['success']:
            self.request.session.flush()
            self.request.user = None

            messages.error(self.request, result['message'])
            return redirect(result['redirect_url'])

        messages.success(self.request, result['message'])
        return redirect(self.get_success_url())


class BaykeShopUserRegisterView(FormView):
    """注册页面"""

    template_name = "baykeshop/member/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("member:login")
    extra_context = {
        "title": _("注册"),
    }

    def form_valid(self, form):
        """注册成功，调用业务服务层"""
        from baykeshop.contrib.member.services.registration import MemberRegistrationService

        # 调用注册服务
        result = MemberRegistrationService.register_user(form, self.request)

        if not result['success']:
            messages.error(self.request, result['message'])
            return self.form_invalid(form)

        user = result['user']
        bayke_user = result['bayke_user']

        # 发送验证邮件（保持现有逻辑）
        result = MemberEmailService.send_verification_email(user, bayke_user, self.request)

        if result['success']:
            messages.success(self.request, _("注册成功！验证邮件已发送到您的邮箱，请查收并验证邮箱后登录。"))
        else:
            messages.success(self.request, _("注册成功！验证邮件发送失败，请稍后重试。"))

        return super().form_valid(form)


class BaykeShopUserLogoutView(LogoutView):
    """登出页面"""

    next_page = reverse_lazy("member:login")

    def get_success_url(self):
        messages.success(self.request, _("登出成功"))
        return super().get_success_url()


class BaykePasswordResetView(PasswordResetView):
    """重置密码"""
    email_template_name = "baykeshop/member/password_reset_email.html"
    success_url = reverse_lazy("member:password_reset_done")
    template_name = "baykeshop/member/password_reset.html"
    form_class = BaykePasswordResetForm


class BaykePasswordResetDoneView(PasswordResetDoneView):
    """重置密码完成"""
    template_name = "baykeshop/member/password_reset_done.html"


class BaykePasswordResetConfirmView(PasswordResetConfirmView):
    """重置密码确认"""
    success_url = reverse_lazy("member:password_reset_complete")
    template_name = "baykeshop/member/password_reset_confirm.html"
    form_class = BaykePasswordResetConfirmForm


class BaykePasswordResetCompleteView(PasswordResetCompleteView):
    """重置密码完成"""
    template_name = "baykeshop/member/password_reset_complete.html"


class EmailVerificationView(View):
    """邮箱验证视图"""
    def get(self, request, token):
        result = MemberVerificationService.verify_email(token)

        if result['success']:
            messages.success(request, result['message'])
            return redirect(result.get('redirect_url', reverse_lazy('member:login')))
        else:
            messages.error(request, result['message'])
            return redirect(result.get('redirect_url', reverse_lazy('member:login')))


class ResendVerificationEmailView(BaykeLoginRequiredMixin, View):
    """重新发送验证邮件视图 — 使用统一 Mixin"""
    def get(self, request):
        try:
            bayke_user = request.user.baykeshopuser

            if bayke_user.is_email_verified:
                messages.warning(request, '您的邮箱已经验证过了。')
                return redirect('member:profile')

            resend_limit_key = f"{bayke_settings.CACHE_PREFIX_EMAIL_RESEND_LIMIT}:{request.user.id}"
            if cache.get(resend_limit_key):
                messages.error(request, "发送过于频繁，请稍后再试")
                return redirect('member:profile')

            result = MemberEmailService.resend_verification_email(request.user, request)

            if result['success']:
                messages.success(request, result['message'])
                return redirect(result.get('redirect_url', reverse_lazy('member:profile')))
            else:
                messages.error(request, result['message'])
                return redirect(result.get('redirect_url', reverse_lazy('member:profile')))

        except Exception as e:
            messages.error(request, "发送验证邮件失败，请稍后再试")
            return redirect('member:profile')


class SendSMSVerificationView(BaykeLoginRequiredMixin, View):
    """发送SMS验证码视图 — 使用统一 Mixin"""
    def post(self, request):
        operation_type = request.POST.get('operation_type', 'general')
        result = MemberSMSAuthService.send_verification_code(request.user, request, operation_type)

        if result['success']:
            messages.success(request, result['message'])
            return redirect(result.get('redirect_url', reverse_lazy('member:profile')))
        else:
            messages.error(request, result['message'])
            return redirect(result.get('redirect_url', reverse_lazy('member:profile')))


class IPVerificationView(View):
    """IP验证视图 — 业务逻辑已下沉到 MemberAuthService.verify_ip_token()"""
    def get(self, request, token):
        result = MemberAuthService.verify_ip_token(token, request)

        if result['success']:
            messages.success(request, result['message'])
        else:
            messages.error(request, result['message'])
        
        return redirect(result['redirect_url'])
