import ipaddress
import json

import django.db.models.deletion
from django.contrib.auth import get_user_model
from django.contrib.sites.managers import CurrentSiteManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from baykeshop.db import BaseModel, BaseUserModel, validators

User = get_user_model()


class BaykeShopUser(BaseUserModel):
    """用户表"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name=_("用户"))     # 与Django内置User模型一对一关联
    is_email_verified = models.BooleanField(default=False, verbose_name=_("邮箱是否验证"))
    email_verified_at = models.DateTimeField(null=True, blank=True, verbose_name=_("邮箱验证时间"))
    verification_token_created_at = models.DateTimeField(null=True, blank=True, verbose_name=_("邮箱验证令牌生成时间"))
    email_verification_token = models.CharField(max_length=64, null=True, blank=True, verbose_name=_("邮箱验证令牌"))
    trusted_ips = models.TextField(default="[]", verbose_name="可信IP列表")
    ip_verify_token = models.CharField(max_length=64, blank=True, null=True, verbose_name="IP验证令牌")
    ip_verify_at = models.DateTimeField(blank=True, null=True, verbose_name="IP验证令牌生成时间")
    ip_verify_target = models.GenericIPAddressField(blank=True, null=True, verbose_name="待验证的IP地址")
    verification_token_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="验证令牌生成IP")
    last_verification_sent_at = models.DateTimeField(blank=True, null=True, verbose_name=_("最后发送验证邮件时间"))
    verification_attempts = models.IntegerField(default=0, verbose_name=_("验证尝试次数"))
    # [新增] 手机号字段（用于敏感操作SMS验证）
    mobile = models.CharField(max_length=11, blank=True, null=True, default="", verbose_name=_("手机号"))

    def __str__(self):
        return self.user.username

    # ============================================================
    # 模型方法 — IP安全相关
    # （middleware.py 和 security.py 依赖这些方法）
    # ============================================================

    def is_ip_trusted(self, ip_address):
        """
        检查IP是否在可信列表中

        IPv4/IPv6 地址自动归一化后再比较，
        避免同一地址的不同文本表示（如 ::ffff:192.168.1.1 vs 192.168.1.1）被误判。

        Args:
            ip_address: 要检查的IP地址

        Returns:
            tuple: (是否可信, 错误信息)
        """
        try:
            normalized = str(ipaddress.ip_address(ip_address.strip()))
        except ValueError:
            normalized = ip_address.strip()

        try:
            trusted_ips = json.loads(self.trusted_ips)
            if not trusted_ips:
                return False, "IP不在可信列表中"
            for tip in trusted_ips:
                try:
                    if str(ipaddress.ip_address(tip.strip())) == normalized:
                        return True, None
                except ValueError:
                    if tip.strip() == normalized:
                        return True, None
            return False, f"IP {ip_address} 不在可信列表中"
        except Exception:
            return False, "可信IP列表解析失败"

    def is_ip_verify_token_valid(self):
        """
        检查IP验证令牌是否24小时内有效

        Returns:
            bool: 令牌是否有效
        """
        from django.utils import timezone
        if not self.ip_verify_at:
            return False
        # 24小时有效期（与配置保持一致）
        expire_seconds = 86400
        return (timezone.now() - self.ip_verify_at).total_seconds() < expire_seconds


class BaykeShopUserAddress(BaseModel):
    """用户地址"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("用户"))
    name = models.CharField(max_length=50, verbose_name=_("收货人"))
    province = models.CharField(max_length=50, verbose_name=_("省"))
    city = models.CharField(max_length=50, verbose_name=_("市"))
    district = models.CharField(max_length=50, verbose_name=_("区"))
    address = models.CharField(max_length=255, verbose_name=_("详细地址"))
    phone = models.CharField(
        max_length=50, verbose_name=_("手机"), validators=[validators.validate_phone]
    )
    email = models.EmailField(verbose_name=_("邮箱"), blank=True, default="")
    is_default = models.BooleanField(default=False, verbose_name=_("是否默认"))

    class Meta:
        verbose_name = _("用户地址")
        verbose_name_plural = verbose_name
        ordering = ["-created_time"]
        indexes = [
            models.Index(fields=["user", "is_default"], name="user_is_default_idx"),
        ]

    def __str__(self):
        return self.name

    def get_full_address(self):
        return f"{self.province}{self.city}{self.district}{self.address}"


class SecurityLog(BaseModel):
    """安全操作日志 - 记录所有安全相关操作"""

    class ActionTypes(models.TextChoices):
        """操作类型枚举"""
        LOGIN = 'LOGIN', _('登录')
        IP_VERIFY = 'IP_VERIFY', _('IP验证')
        REGISTER = 'REGISTER', _('注册')
        BIND_CARD = 'BIND_CARD', _('绑卡')
        PAYMENT = 'PAYMENT', _('支付')
        WITHDRAW = 'WITHDRAW', _('提现')
        CHANGE_PASSWORD = 'CHANGE_PASSWORD', _('修改密码')
        CHANGE_EMAIL = 'CHANGE_EMAIL', _('修改邮箱')
        CHANGE_MOBILE = 'CHANGE_MOBILE', _('修改手机')
        IP_UNTRUSTED_ACCESS = 'IP_UNTRUSTED_ACCESS', _('不可信IP访问')

    class StatusChoices(models.TextChoices):
        """操作状态枚举"""
        SUCCESS = 'success', _('成功')
        FAILED = 'failed', _('失败')

    user = models.ForeignKey(User, on_delete=django.db.models.deletion.CASCADE, verbose_name=_("用户"))
    ip_address = models.GenericIPAddressField(verbose_name=_("IP地址"))
    action_type = models.CharField(
        max_length=50,
        choices=ActionTypes.choices,
        verbose_name=_("操作类型")
    )
    action_detail = models.TextField(verbose_name=_("操作详情"))
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        verbose_name=_("状态")
    )

    current_site = CurrentSiteManager()

    class Meta:
        verbose_name = _("安全日志")
        verbose_name_plural = verbose_name
        ordering = ["-created_time"]
        indexes = [
            models.Index(fields=["user", "-created_time"], name="user_time_idx"),
            models.Index(fields=["ip_address", "-created_time"], name="ip_time_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_action_type_display()} - {self.get_status_display()}"


class UserNotification(BaseModel):
    """用户通知"""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name=_('用户')
    )
    title = models.CharField(max_length=100, verbose_name=_('标题'))
    content = models.TextField(verbose_name=_('内容'), blank=True, default='')
    is_read = models.BooleanField(default=False, verbose_name=_('已读'))
    related_url = models.CharField(
        max_length=255, verbose_name=_('关联链接'), blank=True, default=''
    )

    class Meta:
        verbose_name = _('用户通知')
        verbose_name_plural = _('用户通知')
        ordering = ['-created_time']

    def __str__(self):
        return self.title
