import logging

from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm
)
from django.contrib.auth import password_validation, get_user_model
from django.utils.translation import gettext_lazy as _
from django.template import loader

from baykeshop.forms.mixins import BaseFormMixins
from baykeshop.forms.widgets import WF  # WidgetFactory 别名
from baykeshop.db.validators import sms_code_validator, sms_code_field
from ..tasks import send_reset_password_email_task

logger = logging.getLogger("baykeshop.contrib.member")


class EmailVerificationForm(forms.Form):
    """邮箱验证表单（显示验证状态）"""
    is_verified = forms.BooleanField(required=False, initial=False)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user and hasattr(self.user, 'baykeshopuser'):
            self.fields['is_verified'].initial = self.user.baykeshopuser.is_email_verified


class LoginForm(BaseFormMixins, AuthenticationForm):
    """登录表单"""

    username = forms.CharField(
        label=_("用户名"),
        widget=WF.username_field(),
        required=True,
    )
    password = forms.CharField(
        label=_("密码"),
        widget=WF.password_field(placeholder=_('请输入密码')),
        required=True,
    )


class RegisterForm(BaseFormMixins, UserCreationForm):
    """注册表单"""

    username = forms.CharField(
        label=_("用户名"),
        strip=False,
        widget=WF.username_field(max_length=150),
        max_length=150,
        min_length=6,
        help_text=_("请输入6-16位用户名，只能包含字母、数字、下划线"),
    )
    email = forms.EmailField(
        label=_("邮箱"),
        widget=WF.email_field(help_text=_("请输入正确的邮箱地址，用于虚拟商品接收邮件")),
        required=True,
    )
    phone = forms.CharField(
        label=_("手机号"),
        max_length=50,
        min_length=11,
        required=False,
        widget=WF.phone_field(help_text=_("请输入手机号，用于敏感操作验证")),
    )
    password1 = forms.CharField(
        label=_("Password"),
        widget=WF.password_field(
            placeholder=_('请输入密码'),
            autocomplete="new-password"
        ),
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label=_("Password confirmation"),
        widget=WF.password_field(placeholder=_('请再次输入密码')),
        help_text=_("Enter the same password as before, for verification."),
    )

    class Meta:
        model = get_user_model()
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"]
        User = get_user_model()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                _("邮箱已存在"), code="email_exists"
            )
        return email

    def clean_phone(self):
        """验证手机号唯一性"""
        phone = self.cleaned_data.get("phone", "")

        if phone:
            # 验证手机号长度
            if len(phone) != 11:
                raise forms.ValidationError(_("手机号必须为11位数字"))

            # 验证手机号格式（复用现有验证器）
            from baykeshop.db import validators
            try:
                validators.validate_phone(phone)
            except forms.ValidationError:
                raise forms.ValidationError(_("请输入有效的手机号码"))

            # 检查手机号是否已存在（在BaykeShopUser.mobile字段）
            from baykeshop.contrib.member.models import BaykeShopUser
            if BaykeShopUser.objects.filter(mobile=phone).exists():
                raise forms.ValidationError(_("该手机号已被注册"))

        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class ChangePasswordForm(BaseFormMixins, PasswordChangeForm):
    """修改密码表单 — 使用 Widget 工厂 + SMS 字段工厂"""

    old_password = forms.CharField(
        label=_("Old password"),
        strip=False,
        widget=WF.password_field(
            placeholder=_('请输入旧密码'),
            autocomplete="current-password",
        ),
    )
    new_password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=WF.password_field(
            placeholder=_('请输入新密码'),
            autocomplete="new-password",
        ),
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        widget=WF.password_field(placeholder=_('请再次输入新密码')),
        help_text=_("两次输入的密码不一致时提示此信息。"),  # 国际化修复
    )

    # 使用 SMS 字段工厂，一行搞定（原来 ~18 行）
    sms_code = sms_code_field()

    def clean_sms_code(self):
        """
        SMS验证码格式验证（使用公共验证器）
        """
        code = self.cleaned_data.get('sms_code')
        return sms_code_validator(code)

    def clean(self):
        """表单验证"""
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')

        if new_password1 and new_password2 and new_password1 != new_password2:
            raise forms.ValidationError(_('两次输入的密码不一致'))

        return cleaned_data


class BaykePasswordResetForm(BaseFormMixins, PasswordResetForm):
    """重置密码表单 — 使用 Widget 工厂"""
    email = forms.EmailField(
        label=_("邮箱"),
        widget=WF.email_field(),
    )

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """重置密码邮件发送逻辑，覆盖父类方法实现异步发送"""
        # 渲染邮件主题，去除换行符
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())

        # 渲染纯文本邮件内容
        text_body = loader.render_to_string(email_template_name, context)

        # 渲染HTML邮件内容（如果有）
        html_body = None
        if html_email_template_name is not None:
            html_body = loader.render_to_string(html_email_template_name, context)

        # 调用异步任务
        send_reset_password_email_task.delay(
            subject=subject,
            text_body=text_body,
            to_email=to_email,
            html_body=html_body,
            email_type='password_reset'
        )


class BaykePasswordResetConfirmForm(BaseFormMixins, SetPasswordForm):
    """重置密码确认表单 — 使用 Widget 工厂 + 国际化修复"""

    new_password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=WF.password_field(
            placeholder=_('请输入新密码'),
            autocomplete="new-password",
        ),
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        widget=WF.password_field(placeholder=_('请再次输入新密码')),
        help_text=_("两次输入的密码不一致时提示此信息。"),  # 国际化修复
    )
