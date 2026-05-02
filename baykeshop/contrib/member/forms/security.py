from django import forms
from django.utils.translation import gettext_lazy as _

from baykeshop.db.validators import sms_code_field, sms_code_validator


class SMSVerificationForm(forms.Form):
    """
    SMS验证码表单
    用于敏感操作的短信验证 — 使用 SMS 字段工厂 + 公共验证器
    """
    # 使用字段工厂（原来 ~18 行 → 1 行）
    code = sms_code_field(label=_("验证码"))

    def clean_code(self):
        """验证码格式验证（使用公共验证器）"""
        code = self.cleaned_data.get('code')
        return sms_code_validator(code)
