from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from baykeshop.conf import bayke_settings


def validate_phone(value):
    # 中国区手机号验证
    validators.RegexValidator(
        bayke_settings.REGEX_PHONE, 
        _("手机号码格式有误"), 
        "invalid"
    )(value)


def validate_image_size(value):
    """ 对图片大小进行验证 """
    if value.size > bayke_settings.MAX_IMAGE_SIZE:
        raise ValidationError(
            _("图片大小超过限制"), 
            code='invalid'
        )


class SMSCodeValidator:
    """
    SMS验证码格式公共验证器 — 统一所有表单/序列化器中的SMS验证码校验逻辑

    使用方式（在Form的clean_*方法中）:
        sms_validator = SMSCodeValidator()
        return sms_validator(code)

    或直接作为callable使用:
        field.validators.append(SMSCodeValidator())
    """
    CODE_LENGTH = 6

    def __call__(self, value):
        if not value:
            raise ValidationError('请输入验证码')
        if not value.isdigit():
            raise ValidationError('验证码必须为数字')
        if len(value) != self.CODE_LENGTH:
            raise ValidationError(f'验证码长度为{self.CODE_LENGTH}位')
        return value


# 全局单例，各处直接引用即可
sms_code_validator = SMSCodeValidator()


def sms_code_field(**overrides):
    """
    SMS验证码字段工厂 — 统一3处重复的SMS字段定义
    
    消灭前：每个表单都要写 ~18 行相同的 CharField 定义
    消灭后：一行调用搞定
    
    用法：
        from baykeshop.db.validators import sms_code_field
        
        class MyForm(forms.Form):
            sms_code = sms_code_field()
            
        # 或带覆盖：
            sms_code = sms_code_field(required=False)
    
    Args:
        **overrides: 可覆盖任何 CharField 参数（label, required, widget 等）
    
    Returns:
        forms.CharField: 配置好的SMS验证码字段
    """
    from django import forms as django_forms
    from baykeshop.forms import widgets

    label = overrides.pop('label', _('短信验证码'))
    required = overrides.pop('required', True)

    return django_forms.CharField(
        label=label,
        max_length=6,
        min_length=6,
        required=required,
        widget=widgets.TextInput(
            attrs={
                "placeholder": overrides.pop('placeholder', _("请输入6位验证码")),
                "autocomplete": "off",
                **overrides,
            },
            icon_position='bk-has-icons-left',
            icons_class={"left": "mdi mdi-key", "right": ""},
        ),
        error_messages={
            'required': '请输入验证码',
            'min_length': '验证码长度为6位',
            'max_length': '验证码长度为6位'
        }
    )
