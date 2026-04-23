from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import TemplateView, FormView, UpdateView, ListView, CreateView, DeleteView
from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy

from baykeshop.contrib.member.models import BaykeShopUserAddress, BaykeShopUser
from baykeshop.contrib.member.forms import ChangePasswordForm, BaykeShopUserAddressForm, BaykeShopUserProfileForm
from baykeshop.contrib.member.services.profile import MemberProfileService
from baykeshop.db.security import get_client_ip
from baykeshop.contrib.common.mixins import (
    UserOwnedBaseView,
    AddressFormHandlingMixin,
    BaykeLoginRequiredMixin,
)


class BaykeShopUserProfileView(LoginRequiredMixin, TemplateView):
    """个人中心"""
    template_name = 'baykeshop/member/profile.html'
    extra_context = {'title': _('个人中心')}


class BaykeShopUserPasswordView(BaykeLoginRequiredMixin, SuccessMessageMixin, PasswordChangeView):
    """修改密码 — 使用统一的 BaykeLoginRequiredMixin，无需再声明 login_url"""
    template_name = 'baykeshop/member/password.html'
    extra_context = {'title': _('修改密码')}
    success_url = reverse_lazy('member:profile')
    form_class = ChangePasswordForm
    success_message = _('密码修改成功')


# ============================================================
# 收货地址 CRUD — 使用 Mixin 消灭重复代码
# ============================================================

class BaykeShopUserAddressListView(UserOwnedBaseView, ListView):
    """收货地址列表 — UserOwnedBaseView 自动处理 login_url + 用户隔离"""
    template_name = 'baykeshop/member/address_list.html'
    model = BaykeShopUserAddress
    context_object_name = 'address_list'
    extra_context = {'title': _('收货地址列表')}

    # get_queryset() 由 UserOwnedMixin 自动提供：filter(user=request.user)


class BaykeShopUserAddressCreateView(
    BaykeLoginRequiredMixin, SuccessMessageMixin,
    AddressFormHandlingMixin, CreateView
):
    """新增收货地址 — AddressFormHandlingMixin 统一处理 user 赋值 + 默认地址切换 + next 重定向"""
    template_name = 'baykeshop/member/address_form.html'
    model = BaykeShopUserAddress
    form_class = BaykeShopUserAddressForm
    extra_context = {'title': _('新增收货地址')}
    success_url = reverse_lazy('member:address-list')
    success_message = _('新增收货地址成功')

    def form_valid(self, form):
        # AddressFormHandlingMixin 处理 is_default 切换和 next 重定向
        return super().form_valid(form)


class BaykeShopUserAddressUpdateView(
    BaykeLoginRequiredMixin, SuccessMessageMixin,
    AddressFormHandlingMixin, UpdateView
):
    """修改收货地址 — 与 CreateView 共享相同的 form_valid 逻辑（通过 Mixin）"""
    template_name = 'baykeshop/member/address_form.html'
    model = BaykeShopUserAddress
    form_class = BaykeShopUserAddressForm
    extra_context = {'title': _('修改收货地址')}
    success_url = reverse_lazy('member:address-list')
    success_message = _('修改收货地址成功')

    # get_queryset() 由 AddressFormHandlingMixin → UserOwnedMixin 链式继承自动提供

    def form_valid(self, form):
        # 同样的逻辑！不再重复写
        return super().form_valid(form)


class BaykeShopUserAddressDeleteView(UserOwnedBaseView, SuccessMessageMixin, DeleteView):
    """删除收货地址 — UserOwnedBaseView 自动处理用户隔离"""
    model = BaykeShopUserAddress
    success_url = reverse_lazy('member:address-list')
    success_message = _('删除收货地址成功')

    # get_queryset() 由 UserOwnedMixin 自动提供


class BaykeShopUserProfileUpdateView(BaykeLoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """修改个人资料"""
    template_name = 'baykeshop/member/profile_form.html'
    model = BaykeShopUser
    form_class = BaykeShopUserProfileForm
    extra_context = {'title': _('修改个人资料')}
    success_url = reverse_lazy('member:profile')
    success_message = _('修改个人资料成功')

    def get_object(self):
        instance, _iscreated = BaykeShopUser.objects.get_or_create(
            user=self.request.user, defaults={
                'user': self.request.user,
                'nickname': self.request.user.username
            })
        return instance

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial']['email'] = self.request.user.email
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        client_ip = get_client_ip(self.request)
        user = self.request.user

        if form.cleaned_data.get('email') and form.cleaned_data['email'] != user.email:
            user.email = form.cleaned_data['email']
            user.save()

            result = MemberProfileService.update_email(user, user.email, client_ip, self.request)

            if not result['success']:
                form.add_error('sms_code', result.get('message', '邮箱更新失败'))
                return super().form_valid(form)

        mobile = form.cleaned_data.get('mobile')
        if mobile and mobile != user.baykeshopuser.baykeshopuseraddress_set.filter(is_default=True).first().phone:
            result = MemberProfileService.update_mobile(user, mobile, client_ip, self.request)

            if not result['success']:
                form.add_error('sms_code', result.get('message', '手机号更新失败'))
                return super().form_valid(form)

        return super().form_valid(form)
