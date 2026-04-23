"""
通用视图 Mixin — 消灭重复的 get_queryset / login_url / 用户隔离模式

使用方式：
    class MyView(UserOwnedMixin, ListView):
        model = MyModel
        # 自动获得：
        #   - get_queryset() → filter(user=request.user)
        #   - login_url → 'member:login'
        #   - get_login_url() → 带消息提示
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


class UserOwnedMixin:
    """
    用户数据隔离 Mixin
    自动将 queryset 限制为当前登录用户的数据。
    子类只需设置 model 即可。
    """
    model = None  # 子类必须设置

    def get_queryset(self):
        """自动过滤为当前用户数据"""
        queryset = super().get_queryset()
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            return queryset.filter(user=self.request.user)
        return queryset


class BaykeLoginRequiredMixin(LoginRequiredMixin):
    """
    统一登录要求 Mixin
    - 全局 login_url（无需每个视图声明）
    - 未登录时自动提示
    """
    login_url = reverse_lazy('member:login')

    def get_login_url(self):
        messages.warning(self.request, _('请先登录后操作！'))
        return super().get_login_url()


class UserOwnedBaseView(BaykeLoginRequiredMixin, UserOwnedMixin):
    """
    组合：登录验证 + 用户数据隔离
    大部分 Member/Shop 视图可直接继承此基类。
    
    用法：
        class OrderListView(UserOwnedBaseView, ListView):
            model = BaykeShopOrders
            # 不需要写 get_queryset、login_url、get_login_url
    """
    pass


class AddressFormHandlingMixin:
    """
    收货地址表单处理 Mixin
    统一处理地址新增/修改时的：
    - form.instance.user 赋值
    - is_default 切换逻辑（新默认地址时清除旧标记）
    - next 重定向支持
    """
    redirect_field_name = 'next'

    def get_success_url(self):
        return self.request.GET.get(self.redirect_field_name) or self.success_url

    def form_valid(self, form):
        form.instance.user = self.request.user
        if form.cleaned_data.get('is_default'):
            from baykeshop.contrib.member.models import BaykeShopUserAddress
            BaykeShopUserAddress.objects.filter(
                user=self.request.user,
                is_default=True
            ).update(is_default=False)
        return super().form_valid(form)
