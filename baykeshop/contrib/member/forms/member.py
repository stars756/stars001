from django import forms
from django.utils.translation import gettext_lazy as _

from baykeshop.forms.mixins import BaseFormMixins
from baykeshop.forms.widgets import WF, WidgetFactory, TextInput  # 工厂方法 + 地址字段 + 基础输入框
from baykeshop.db.validators import sms_code_validator, sms_code_field
from baykeshop.contrib.shop.models import BaykeShopOrdersComment
from baykeshop.contrib.member.models import BaykeShopUserAddress, BaykeShopUser


class BaykeShopUserAddressForm(BaseFormMixins, forms.ModelForm):
    """ 收货地址表单 — 使用 WidgetFactory 消灭重复配置 """

    class Meta:
        model = BaykeShopUserAddress
        fields = ['name', 'phone', 'province', 'city', 'district', 'address', 'email', 'is_default']
        widgets = {
            'name': WF.nickname_field(placeholder=_('请输入收货人'), icons_class={'left': 'mdi mdi-account', 'right': ''}),
            'phone': WF.phone_field(),
            'province': WidgetFactory.address_text_field(_('请输入省')),
            'city': WidgetFactory.address_text_field(_('请输入市')),
            'district': WidgetFactory.address_text_field(_('请输入区')),
            'address': WidgetFactory.address_text_field(_('请输入详细地址')),
            'email': WF.email_field(),
        }


class BaykeShopUserProfileForm(BaseFormMixins, forms.ModelForm):
    """ 个人资料表单 — 使用 Widget工厂 + SMS字段工厂 """

    email = forms.EmailField(
        label=_("邮箱"),
        widget=WF.email_field(),
    )

    # 使用 SMS 字段工厂（原来 ~20 行 → 1 行）
    sms_code = sms_code_field()

    def clean_sms_code(self):
        """
        SMS验证码格式验证（使用公共验证器）
        """
        code = self.cleaned_data.get('sms_code')
        return sms_code_validator(code)

    class Meta:
        model = BaykeShopUser
        fields = ['avatar', 'gender', 'nickname', 'email', 'mobile', 'qq', 'wechat', 'description', 'sms_code']
        widgets = {
            'nickname': WF.nickname_field(),
            'mobile': WF.phone_field(placeholder=_('请输入手机号码')),
            'gender': forms.Select(
                attrs={'placeholder': _('请选择性别')},
            ),
            'birthday': forms.DateInput(attrs={'type': 'date', 'class': 'bk-input'}, format='%Y-%m-%d'),
            'qq': TextInput(
                attrs={'placeholder': _('请输入QQ')},
                icon_position='bk-has-icons-left',
                icons_class={'left': 'mdi mdi-qqchat', 'right': ''}
            ),
            'wechat': TextInput(
                attrs={'placeholder': _('请输入微信')},
                icon_position='bk-has-icons-left',
                icons_class={'left': 'mdi mdi-wechat', 'right': ''}
            ),
            'description': forms.Textarea(
                attrs={'placeholder': _('请输入简介'), 'class': 'bk-textarea bk-has-fixed-size'},
            )
        }




class BaykeShopOrdersCommentForm(BaseFormMixins, forms.ModelForm):
    """订单评论表单"""

    class Meta:
        model = BaykeShopOrdersComment
        fields = ('content', 'score',)
        widgets = {
            'content': forms.Textarea(
                attrs={'placeholder': _('请输入评论内容'), 'class': 'bk-textarea', 'rows': 5, 'cols': 50},
            ),
            'score': forms.Select(
                attrs={'placeholder': _('请选择评分')},
            )
        }
