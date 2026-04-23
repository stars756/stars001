from django.forms import widgets
from django.utils.translation import gettext_lazy as _


class Input(widgets.Input):

    template_name = "baykeshop/forms/widgets/input.html"

    def __init__(self, attrs=None, icon_position=None, icons_class=None):
        super().__init__(attrs)
        # 图标位置bk-has-icons-left bk-has-icons-right
        self.icon_position = icon_position or ""
        self.icons_class = icons_class or {"left": "", "right": ""}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["icon_position"] = self.icon_position
        context["icons_class"] = self.icons_class
        return context

    def build_attrs(self, base_attrs, extra_attrs=None):
        extra_attrs.update({"class": "bk-input"})
        return super().build_attrs(base_attrs, extra_attrs)


class TextInput(Input):
    """文本输入框"""

    input_type = "text"
    template_name = "baykeshop/forms/widgets/text.html"


class PasswordInput(Input):
    """密码输入框"""

    input_type = "password"
    template_name = "baykeshop/forms/widgets/password.html"

    def __init__(
        self, attrs=None, icon_position=None, icons_class=None, render_value=False
    ):
        super().__init__(attrs, icon_position, icons_class)
        self.render_value = render_value

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["render_value"] = self.render_value
        return context


class Select(widgets.Select):
    """下拉框"""

    template_name = "baykeshop/forms/widgets/select.html"

    def __init__(
        self,
        attrs=None,
        choices=(),
        icon_position=None,
        icons_class=None,
        select_class=None,
    ):
        super().__init__(attrs, choices)
        self.icon_position = icon_position or ""
        self.icons_class = icons_class or {"left": "", "right": ""}
        self.select_class = select_class or ""

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["icon_position"] = self.icon_position
        context["icons_class"] = self.icons_class
        return context


class RichTextWidget(widgets.Textarea):
    """富文本"""

    template_name = "baykeshop/forms/widgets/richtext.html"

    class Media:
        js = ("baykeshop/tinymce/tinymce.min.js",)


# ============================================================
# 预定义字段组件工厂 — 消灭表单中重复的 widget 配置
# ============================================================

class WidgetFactory:
    """
    常用表单字段 Widget 工厂方法
    统一管理 icon_position、icons_class、autocomplete 等配置，
    避免每个表单重复写 5-8 行相同配置。
    
    用法：
        from baykeshop.forms.widgets import WidgetFactory as WF
        
        email = forms.EmailField(
            label=_("邮箱"),
            widget=WF.email_field(overrides={'placeholder': '自定义'})
        )
        
        phone = forms.CharField(
            label=_("手机"),
            widget=WF.phone_field()
        )
    """

    @staticmethod
    def _base_attrs(**overrides):
        """基础属性合并，允许子类覆盖"""
        return {**overrides}

    @staticmethod
    def email_field(**overrides):
        """邮箱输入框（带邮箱icon + autocomplete）"""
        attrs = {
            'placeholder': overrides.pop('placeholder', _('请输入邮箱')),
            "autocomplete": "email",
            'type': 'email',
            **overrides,
        }
        return TextInput(
            attrs=attrs,
            icon_position='bk-has-icons-left',
            icons_class={'left': 'mdi mdi-email', 'right': ''}
        )

    @staticmethod
    def phone_field(**overrides):
        """手机号输入框（带手机icon + tel type）"""
        attrs = {
            'placeholder': overrides.pop('placeholder', _('请输入手机号')),
            "autocomplete": "tel",
            'type': 'tel',
            **overrides,
        }
        return TextInput(
            attrs=attrs,
            icon_position='bk-has-icons-left',
            icons_class={'left': 'mdi mdi-cellphone', 'right': ''}
        )

    @staticmethod
    def password_field(**overrides):
        """密码输入框（带锁icon + autocomplete off）"""
        attrs = {
            'placeholder': overrides.pop('placeholder', _('请输入密码')),
            "autocomplete": overrides.pop('autocomplete', 'off'),
            **overrides,
        }
        return PasswordInput(
            attrs=attrs,
            icon_position='bk-has-icons-left',
            icons_class={'left': 'mdi mdi-lock', 'right': ''}
        )

    @staticmethod
    def username_field(**overrides):
        """用户名输入框（带用户icon + autofocus）"""
        attrs = {
            'placeholder': overrides.pop('placeholder', _('请输入用户名')),
            "autofocus": True,
            **overrides,
        }
        return TextInput(
            attrs=attrs,
            icon_position='bk-has-icons-left bk-has-icons-right',
            icons_class={"left": "mdi mdi-account", "right": "mdi mdi-check"},
        )

    @staticmethod
    def nickname_field(**overrides):
        """昵称输入框"""
        attrs = {
            'placeholder': overrides.pop('placeholder', _('请输入昵称')),
            **overrides,
        }
        return TextInput(
            attrs=attrs,
            icon_position='bk-has-icons-left',
            icons_class={'left': 'mdi mdi-account', 'right': ''},
        )

    @staticmethod
    def address_text_field(placeholder, **overrides):
        """地址相关文本框（省/市/区/详细地址，带地图icon）"""
        attrs = {'placeholder': placeholder, **overrides}
        return TextInput(
            attrs=attrs,
            icon_position='bk-has-icons-left',
            icons_class={'left': 'mdi mdi-map-marker', 'right': ''}
        )


# 简短别名，表单中直接用 WF 调用
WF = WidgetFactory
