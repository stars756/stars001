"""
安全验证模块 — 统一的安全检查工具集

纯工具函数已提取至 baykeshop.utils.*：
- get_client_ip           → baykeshop.utils.ip
- SMS code/rate           → baykeshop.utils.sms
- verification_token      → baykeshop.utils.tokens
- security_logger         → baykeshop.utils.security_log

本文件保留依赖 BaykeShopUser 模型的函数，并从 utils 重新导出以保持向后兼容。
"""
import ipaddress
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from baykeshop.conf import bayke_settings
from baykeshop.contrib.member.models import BaykeShopUser, SecurityLog
from baykeshop.contrib.member.tasks import send_email_verification_task

# 从 utils 重新导出纯工具函数（向后兼容）
from baykeshop.utils.ip import get_client_ip
from baykeshop.utils.security_log import security_logger
from baykeshop.utils.sms import (
    cache_sms_code,
    check_sms_rate_limit,
    generate_sms_code,
    get_sms_cache_key,
    increment_sms_rate_limit,
)
from baykeshop.utils.tokens import generate_verification_token

__all__ = [
    "get_client_ip",
    "generate_sms_code", "cache_sms_code", "check_sms_rate_limit", "increment_sms_rate_limit",
    "generate_verification_token",
    "security_logger",
    "check_verification_lockout", "verify_sms_code", "verify_sms_code_from_request",
    "verify_user_extensions", "check_email_verified", "check_ip_trusted", "check_phone_bound",
    "record_security_operation",
    "send_verification_email_to_user",
    "is_ip_trusted", "add_trusted_ip", "clear_trusted_ips",
    "is_verification_token_valid", "is_email_verification_token_valid",
    "increment_verification_attempts", "reset_verification_attempts",
]

logger = logging.getLogger("baykeshop.contrib.member")


# ============================================================
# 验证锁定
# ============================================================

def check_verification_lockout(bayke_user):
    """检查验证码是否已被锁定（失败次数过多）"""
    max_attempts = bayke_settings.MAX_VERIFICATION_ATTEMPTS
    if bayke_user.verification_attempts >= max_attempts:
        lockout_minutes = bayke_settings.VERIFICATION_LOCKOUT_SECONDS // 60
        return False, f'验证失败次数过多，请{lockout_minutes}分钟后再试'
    return True, None


# ============================================================
# SMS 验证码验证（依赖 BaykeShopUser 模型）
# ============================================================

def verify_sms_code(user_id, code, operation_type):
    """
    验证用户输入的SMS验证码是否正确

    验证失败递增尝试计数器，超过上限后锁定账户
    """
    try:
        bayke_user = BaykeShopUser.objects.get(user_id=user_id)
    except BaykeShopUser.DoesNotExist:
        return False

    ok, msg = check_verification_lockout(bayke_user)
    if not ok:
        return False

    cache_key = get_sms_cache_key(user_id, operation_type)
    cached_code = cache.get(cache_key)

    if cached_code and cached_code == code:
        cache.delete(cache_key)
        reset_verification_attempts(bayke_user)
        return True
    increment_verification_attempts(bayke_user)
    return False


def verify_sms_code_from_request(request, user_id, operation_type, error_message="验证码错误"):
    """
    从请求中验证SMS验证码（供服务层和表单使用）
    """
    if request is None or 'sms_code' not in request.POST:
        return False, '请输入SMS验证码'

    try:
        bayke_user = BaykeShopUser.objects.get(user_id=user_id)
        ok, lock_msg = check_verification_lockout(bayke_user)
        if not ok:
            return False, lock_msg
    except BaykeShopUser.DoesNotExist:
        pass

    sms_code = request.POST.get('sms_code', '').strip()

    code_length = bayke_settings.SMS_CODE_LENGTH
    if not sms_code.isdigit():
        return False, '验证码必须为数字'
    if len(sms_code) != code_length:
        return False, f'验证码长度为{code_length}位'

    cache_key = get_sms_cache_key(user_id, operation_type)
    expected_code = cache.get(cache_key)

    if not expected_code or expected_code != sms_code:
        try:
            bayke_user = BaykeShopUser.objects.get(user_id=user_id)
            increment_verification_attempts(bayke_user)
        except BaykeShopUser.DoesNotExist:
            pass
        security_logger.warning(
            "SMS_VERIFY_FAILED | user_id=%s | op=%s | ip=%s | attempts_incremented=True",
            user_id, operation_type,
            request.META.get('REMOTE_ADDR', 'unknown') if request else 'unknown'
        )
        return False, error_message

    cache.delete(cache_key)
    try:
        bayke_user = BaykeShopUser.objects.get(user_id=user_id)
        reset_verification_attempts(bayke_user)
    except BaykeShopUser.DoesNotExist:
        pass

    return True, None


# ============================================================
# 业务检查函数（供装饰器和服务层使用）
# ============================================================

def verify_user_extensions(request, error_message="用户信息异常，请重新登录"):
    """获取用户扩展信息（供装饰器使用）"""
    if not request.user.is_authenticated:
        messages.error(request, "请先登录")
        return redirect(reverse('member:login'))

    try:
        return BaykeShopUser.objects.get(user=request.user)
    except BaykeShopUser.DoesNotExist:
        messages.error(request, error_message)
        return None


def check_email_verified(bayke_user):
    """检查邮箱是否已验证"""
    if not bayke_user.is_email_verified:
        return False, '邮箱未验证，请先验证邮箱'
    return True, None


def check_ip_trusted(bayke_user, ip_address):
    """检查IP是否可信（委托给模型方法或模块级函数）"""
    if hasattr(bayke_user, 'is_ip_trusted') and callable(getattr(bayke_user, 'is_ip_trusted')):
        result = bayke_user.is_ip_trusted(ip_address)
        if isinstance(result, tuple):
            if not result[0]:
                security_logger.warning(
                    "IP_NOT_TRUSTED | user=%s | ip=%s | detail=%s",
                    bayke_user.user.username, ip_address, result[1]
                )
            return result
        if not result:
            security_logger.warning(
                "IP_NOT_TRUSTED | user=%s | ip=%s | detail=当前IP不可信，请先验证IP",
                bayke_user.user.username, ip_address
            )
        return (result, None) if result else (False, '当前IP不可信，请先验证IP')

    is_trusted, message = is_ip_trusted(bayke_user, ip_address)
    if not is_trusted:
        security_logger.warning(
            "IP_NOT_TRUSTED | user=%s | ip=%s | detail=%s",
            bayke_user.user.username, ip_address, message or '当前IP不可信'
        )
        return False, message or '当前IP不可信'

    return True, None


def check_phone_bound(bayke_user):
    """检查手机号是否已绑定"""
    if not hasattr(bayke_user, 'mobile') or not bayke_user.mobile:
        has_phone = bayke_user.user.baykeshopuseraddress_set.filter(is_default=True).exists()
        if not has_phone:
            return False, '请先绑定手机号'
    return True, None


# ============================================================
# 安全日志记录
# ============================================================

def record_security_operation(bayke_user, action_type, action_detail, ip_address):
    """记录安全操作（DB + security.log 双写）"""
    SecurityLog.objects.create(
        user=bayke_user.user,
        ip_address=ip_address,
        action_type=action_type,
        action_detail=action_detail,
        status=SecurityLog.StatusChoices.SUCCESS
    )
    security_logger.info(
        "SECURITY_EVENT | user=%s | ip=%s | action=%s | detail=%s",
        bayke_user.user.username, ip_address, action_type, action_detail
    )


# ============================================================
# 邮件发送服务
# ============================================================

def send_verification_email_to_user(user, request, client_ip, bayke_user):
    """发送验证邮件（Django 模板渲染，自动转义防 XSS）"""
    email_verify_prefix = bayke_settings.CACHE_PREFIX_EMAIL_VERIFY_LIMIT
    email_resend_prefix = bayke_settings.CACHE_PREFIX_EMAIL_RESEND_LIMIT
    verify_cooldown = bayke_settings.EMAIL_VERIFY_COOLDOWN_SECONDS
    resend_cooldown = bayke_settings.EMAIL_RESEND_COOLDOWN_SECONDS

    cache.delete(f"{email_resend_prefix}:{user.id}")
    cache.delete(f"{email_verify_prefix}:{user.email}")

    bayke_user.last_verification_sent_at = timezone.now()
    bayke_user.verification_token_ip = client_ip
    bayke_user.save()

    token = generate_verification_token()
    bayke_user.email_verification_token = token
    bayke_user.email_verify_at = timezone.now()
    bayke_user.save()

    verify_url = reverse("member:verify_email", kwargs={"token": token})
    full_verify_url = request.build_absolute_uri(verify_url)

    email_subject_prefix = getattr(settings, 'EMAIL_SUBJECT_PREFIX', '[baykeShop]')
    subject = f"{email_subject_prefix}{_('邮箱验证')}"

    template_context = {
        'username': user.username,
        'verification_url': full_verify_url,
        'subject': subject,
    }

    text_body = render_to_string('baykeshop/email/verification.txt', template_context)
    html_body = render_to_string('baykeshop/email/verification.html', template_context)

    send_email_verification_task.delay(
        subject=subject, text_body=text_body, to_email=user.email,
        html_body=html_body, email_type='verification'
    )

    cache.set(f"{email_verify_prefix}:{user.email}", 1, timeout=verify_cooldown)
    cache.set(f"{email_resend_prefix}:{user.id}", 1, timeout=resend_cooldown)

    logger.info("邮箱验证邮件任务已提交到队列，发送至 %s", user.email)

    return {'success': True, 'verify_url': full_verify_url}


# ============================================================
# IP可信列表管理
# ============================================================

def is_ip_trusted(bayke_user, ip_address):
    """检查IP是否在可信列表中（模块级函数）"""
    try:
        trusted_ips = json.loads(bayke_user.trusted_ips)
        if not trusted_ips:
            return False, "IP不在可信列表中"
        if ip_address in trusted_ips:
            return True, None
        return False, f"IP {ip_address} 不在可信列表中"
    except Exception:
        return False, "可信IP列表解析失败"


def add_trusted_ip(bayke_user, ip_address):
    """添加IP到可信列表（存储前归一化）"""
    try:
        normalized = str(ipaddress.ip_address(ip_address.strip()))
    except ValueError:
        normalized = ip_address.strip()

    try:
        trusted_ips = json.loads(bayke_user.trusted_ips)
        if normalized not in trusted_ips:
            trusted_ips.append(normalized)
            bayke_user.trusted_ips = json.dumps(trusted_ips)
            bayke_user.save()
    except Exception:
        bayke_user.trusted_ips = json.dumps([normalized])
        bayke_user.save()


def clear_trusted_ips(bayke_user):
    """清空可信IP列表"""
    bayke_user.trusted_ips = "[]"
    bayke_user.save()


# ============================================================
# Token 验证
# ============================================================

def is_verification_token_valid(bayke_user, token):
    """验证令牌是否匹配"""
    return bayke_user.email_verification_token == token


def is_email_verification_token_valid(bayke_user):
    """检查邮箱验证令牌是否在有效期内"""
    if not bayke_user.email_verify_at:
        return False
    expire_seconds = bayke_settings.EMAIL_VERIFY_TOKEN_EXPIRE_SECONDS
    return (timezone.now() - bayke_user.email_verify_at).total_seconds() < expire_seconds


# ============================================================
# 验证尝试次数管理
# ============================================================

def increment_verification_attempts(bayke_user):
    """增加验证尝试次数"""
    bayke_user.verification_attempts = bayke_user.verification_attempts + 1
    bayke_user.save()


def reset_verification_attempts(bayke_user):
    """重置验证尝试次数"""
    bayke_user.verification_attempts = 0
    bayke_user.save()
