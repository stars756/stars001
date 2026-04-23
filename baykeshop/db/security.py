"""
安全验证模块 — 统一的安全检查工具集

职责划分（重构后）:
- IP工具函数 → 本文件（get_client_ip）
- SMS验证码服务 → 本文件（生成/缓存/验证/限流）
- 业务检查函数 → 本文件（邮箱/IP/手机号检查，供装饰器和服务层调用）
- 邮件发送 → 本文件 + contrib/member/tasks.py（通用异步任务）
- Token工具 → 本文件（生成/验证令牌）
- IP可信列表管理 → 本文件 + 模型方法

配置来源: baykeshop.conf.defaults 中的 SECURITY_* 配置项
"""
import json
import logging
import random
import secrets

from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages

from baykeshop.contrib.member.models import BaykeShopUser, SecurityLog
from baykeshop.contrib.member.tasks import send_email_verification_task
from baykeshop.conf import bayke_settings

logger = logging.getLogger("baykeshop.contrib.member")

# 专用安全日志记录器（输出到 security.log）
security_logger = logging.getLogger("baykeshop.security")


# ============================================================
# 工具函数：IP获取
# ============================================================

def get_client_ip(request):
    """
    获取用户真实IP地址

    支持代理服务器场景，优先获取 X-Forwarded-For 头中的真实IP

    Args:
        request: Django HttpRequest 对象或None

    Returns:
        str: 客户端真实IP地址或"unknown"
    """
    if request is None:
        return "unknown"

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ============================================================
# SMS验证码服务
# ============================================================

def _get_sms_cache_key(user_id, operation_type):
    """获取SMS验证码的Redis缓存键"""
    prefix = bayke_settings.CACHE_PREFIX_SMS_VERIFY
    return f"{prefix}:{user_id}:{operation_type}"


def _get_sms_minute_rate_key(user_id, operation_type):
    """获取1分钟限流键"""
    prefix = bayke_settings.CACHE_PREFIX_SMS_RATE_MINUTE
    return f"{prefix}:{user_id}:{operation_type}"


def _get_sms_hour_rate_key(user_id, operation_type):
    """获取1小时限流键"""
    prefix = bayke_settings.CACHE_PREFIX_SMS_RATE_HOUR
    return f"{prefix}:{user_id}:{operation_type}"


def generate_sms_code():
    """
    生成数字验证码（长度从配置读取）

    Returns:
        str: 数字验证码字符串
    """
    length = bayke_settings.SMS_CODE_LENGTH
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])


def cache_sms_code(user_id, code, operation_type):
    """
    将SMS验证码缓存到Redis

    过期时间从配置读取（默认5分钟）

    Args:
        user_id: 用户ID
        code: 验证码
        operation_type: 操作类型（如 'CHANGE_PASSWORD', 'PAYMENT' 等）

    Returns:
        str: Redis缓存键
    """
    cache_key = _get_sms_cache_key(user_id, operation_type)
    expire_seconds = bayke_settings.SMS_CODE_EXPIRE_SECONDS
    cache.set(cache_key, code, expire_seconds)
    return cache_key


def verify_sms_code(user_id, code, operation_type):
    """
    验证用户输入的SMS验证码是否正确

    验证成功后会自动删除缓存的验证码（一次性使用）

    Args:
        user_id: 用户ID
        code: 用户输入的验证码
        operation_type: 操作类型

    Returns:
        bool: 验证码是否正确
    """
    cache_key = _get_sms_cache_key(user_id, operation_type)
    cached_code = cache.get(cache_key)

    if cached_code and cached_code == code:
        # 验证成功，删除缓存的验证码
        cache.delete(cache_key)
        return True
    return False


def check_sms_rate_limit(user_id, operation_type):
    """
    检查SMS发送频率限制

    限流规则从配置读取（默认：1分钟1次，1小时5次）

    Args:
        user_id: 用户ID
        operation_type: 操作类型

    Returns:
        tuple: (是否允许发送, 错误信息)
    """
    minute_key = _get_sms_minute_rate_key(user_id, operation_type)
    hour_key = _get_sms_hour_rate_key(user_id, operation_type)

    minute_limit = bayke_settings.SMS_RATE_LIMIT_MINUTE
    hour_limit = bayke_settings.SMS_RATE_LIMIT_HOUR

    minute_count = cache.get(minute_key, 0)
    hour_count = cache.get(hour_key, 0)

    if minute_count >= minute_limit:
        security_logger.warning(
            "SMS_RATE_LIMITED | user_id=%s | op=%s | window=minute | count=%d/%d",
            user_id, operation_type, minute_count, minute_limit
        )
        return False, "发送过于频繁，请1分钟后再试"

    if hour_count >= hour_limit:
        security_logger.warning(
            "SMS_RATE_LIMITED | user_id=%s | op=%s | window=hourly | count=%d/%d",
            user_id, operation_type, hour_count, hour_limit
        )
        return False, f"今日发送次数已达上限，请{bayke_settings.SMS_RATE_HOUR_WINDOW // 3600}小时后再试"

    return True, None


def increment_sms_rate_limit(user_id, operation_type):
    """
    增加SMS发送计数

    窗口时间从配置读取

    Args:
        user_id: 用户ID
        operation_type: 操作类型
    """
    minute_key = _get_sms_minute_rate_key(user_id, operation_type)
    hour_key = _get_sms_hour_rate_key(user_id, operation_type)

    minute_window = bayke_settings.SMS_RATE_MINUTE_WINDOW
    hour_window = bayke_settings.SMS_RATE_HOUR_WINDOW

    # 1分钟计数
    cache.set(minute_key, cache.get(minute_key, 0) + 1, minute_window)

    # 1小时计数
    cache.set(hour_key, cache.get(hour_key, 0) + 1, hour_window)


# ============================================================
# 业务检查函数（供装饰器和服务层使用）
# ============================================================

def verify_user_extensions(request, error_message="用户信息异常，请重新登录"):
    """
    获取用户扩展信息（供装饰器使用）

    Args:
        request: Django HttpRequest 对象
        error_message: 错误消息

    Returns:
        BaykeShopUser or None: 用户扩展对象或None（失败时）
    """

    if not request.user.is_authenticated:
        messages.error(request, "请先登录")
        return redirect(reverse('member:login'))

    try:
        return BaykeShopUser.objects.get(user=request.user)
    except BaykeShopUser.DoesNotExist:
        messages.error(request, error_message)
        return None


def check_email_verified(bayke_user):
    """
    检查邮箱是否已验证（供装饰器和服务层使用）

    Args:
        bayke_user: BaykeShopUser 对象

    Returns:
        tuple: (是否验证, 错误信息)
    """
    if not bayke_user.is_email_verified:
        return False, '邮箱未验证，请先验证邮箱'

    return True, None


def check_ip_trusted(bayke_user, ip_address):
    """
    检查IP是否可信（委托给模型方法或模块级函数）

    Args:
        bayke_user: BaykeShopUser 对象
        ip_address: IP地址

    Returns:
        tuple: (是否可信, 错误信息)
    """
    # 优先使用模型方法（如果有）
    if hasattr(bayke_user, 'is_ip_trusted') and callable(getattr(bayke_user, 'is_ip_trusted')):
        result = bayke_user.is_ip_trusted(ip_address)
        if isinstance(result, tuple):
            # IP 不信任时记录安全日志
            if not result[0]:
                security_logger.warning(
                    "IP_NOT_TRUSTED | user=%s | ip=%s | detail=%s",
                    bayke_user.user.username, ip_address, result[1]
                )
            return result
        # 如果返回的是布尔值，包装为tuple
        if not result:
            security_logger.warning(
                "IP_NOT_TRUSTED | user=%s | ip=%s | detail=当前IP不可信，请先验证IP",
                bayke_user.user.username, ip_address
            )
        return (result, None) if result else (False, '当前IP不可信，请先验证IP')

    # 回退到模块级函数
    is_trusted, message = is_ip_trusted(bayke_user, ip_address)
    if not is_trusted:
        security_logger.warning(
            "IP_NOT_TRUSTED | user=%s | ip=%s | detail=%s",
            bayke_user.user.username, ip_address, message or '当前IP不可信'
        )
        return False, message or '当前IP不可信'

    return True, None


def check_phone_bound(bayke_user):
    """
    检查手机号是否已绑定

    [Bug修复] 原实现错误地检查了地址表而非mobile字段，
    现在改为正确检查bayke_user.mobile字段

    Args:
        bayke_user: BaykeShopUser 对象

    Returns:
        tuple: (是否绑定, 错误信息)
    """
    # 修复：直接检查 mobile 字段，而不是查地址表
    if not hasattr(bayke_user, 'mobile') or not bayke_user.mobile:
        # 回退：如果没有mobile字段，检查默认地址中的手机号
        has_phone = bayke_user.user.baykeshopuseraddress_set.filter(is_default=True).exists()
        if not has_phone:
            return False, '请先绑定手机号'

    return True, None


# ============================================================
# 从请求验证SMS（供服务层使用）
# ============================================================

def verify_sms_code_from_request(request, user_id, operation_type, error_message="验证码错误"):
    """
    从请求中验证SMS验证码（供服务层和表单使用）

    注意：此函数同时包含格式校验和业务校验，
    格式校验部分建议逐步迁移到 SMSCodeValidator

    Args:
        request: Django HttpRequest 对象或None
        user_id: 用户ID
        operation_type: 操作类型
        error_message: 错误消息

    Returns:
        tuple: (是否成功, 错误信息)
    """

    if request is None or 'sms_code' not in request.POST:
        return False, '请输入SMS验证码'

    sms_code = request.POST.get('sms_code', '').strip()

    # 验证码格式校验（与 SMSCodeValidator 保持一致）
    code_length = bayke_settings.SMS_CODE_LENGTH
    if not sms_code.isdigit():
        return False, '验证码必须为数字'
    if len(sms_code) != code_length:
        return False, f'验证码长度为{code_length}位'

    # 验证验证码
    cache_key = _get_sms_cache_key(user_id, operation_type)
    expected_code = cache.get(cache_key)

    if not expected_code or expected_code != sms_code:
        # 增加尝试次数
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

    # 验证成功，清空验证码
    cache.delete(cache_key)
    try:
        bayke_user = BaykeShopUser.objects.get(user_id=user_id)
        reset_verification_attempts(bayke_user)
    except BaykeShopUser.DoesNotExist:
        pass

    return True, None


# ============================================================
# 安全日志记录
# ============================================================

def record_security_operation(bayke_user, action_type, action_detail, ip_address):
    """
    记录安全操作（供装饰器和服务层使用）

    同时写入 DB 安全日志表 和 security.log 文件

    Args:
        bayke_user: BaykeShopUser 对象
        action_type: 操作类型（SecurityLog.ActionTypes）
        action_detail: 操作详情
        ip_address: IP地址
    """
    # 写入数据库
    SecurityLog.objects.create(
        user=bayke_user.user,
        ip_address=ip_address,
        action_type=action_type,
        action_detail=action_detail,
        status=SecurityLog.StatusChoices.SUCCESS
    )
    # 写入安全日志文件（结构化格式，方便审计和告警）
    security_logger.info(
        "SECURITY_EVENT | user=%s | ip=%s | action=%s | detail=%s",
        bayke_user.user.username, ip_address, action_type, action_detail
    )


# ============================================================
# 邮件发送服务
# ============================================================

def send_verification_email_to_user(user, request, client_ip, bayke_user):
    """
    发送验证邮件（供注册和重发使用）

    [改进] HTML模板仍然内联（后续版本应迁移到模板文件），
    但配置值已全部收敛到 bayke_settings

    Args:
        user: User对象
        request: HttpRequest对象
        client_ip: 客户端IP
        bayke_user: BaykeShopUser 对象

    Returns:
        dict: 发送结果
    """
    from django.utils.translation import gettext as _
    from django.conf import settings

    # 缓存键使用配置前缀
    email_verify_prefix = bayke_settings.CACHE_PREFIX_EMAIL_VERIFY_LIMIT
    email_resend_prefix = bayke_settings.CACHE_PREFIX_EMAIL_RESEND_LIMIT
    verify_cooldown = bayke_settings.EMAIL_VERIFY_COOLDOWN_SECONDS
    resend_cooldown = bayke_settings.EMAIL_RESEND_COOLDOWN_SECONDS

    # 清除频率限制
    cache.delete(f"{email_resend_prefix}:{user.id}")
    cache.delete(f"{email_verify_prefix}:{user.email}")

    # 更新发送时间
    bayke_user.last_verification_sent_at = timezone.now()
    bayke_user.verification_token_ip = client_ip
    bayke_user.save()

    # 生成token
    token = generate_verification_token()

    # 保存token
    bayke_user.email_verification_token = token
    bayke_user.email_verify_at = timezone.now()
    bayke_user.save()

    # 构建验证URL
    verify_url = reverse("member:verify_email", kwargs={"token": token})
    full_verify_url = request.build_absolute_uri(verify_url)

    # 生成邮件主题和内容
    email_subject_prefix = getattr(settings, 'EMAIL_SUBJECT_PREFIX', '[baykeShop]')
    subject = f"{email_subject_prefix}{_('邮箱验证')}"

    # 纯文本邮件内容
    text_body = _(
        "您好 {username}，\n\n"
        "请点击以下链接验证您的邮箱：\n"
        "{verification_url}\n\n"
        "如果链接无法点击，请复制链接到浏览器地址栏中访问。\n"
        "此链接24小时内有效。\n\n"
        "如果您没有请求验证邮箱，请忽略此邮件。\n\n"
        "感谢使用我们的服务！\n"
        "baykeShop团队"
    ).format(
        username=user.username,
        verification_url=full_verify_url
    )

    # HTML邮件内容（TODO: 后续版本迁移到 templates/baykeshop/email/ 目录）
    html_body = _(
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        '    <meta charset="utf-8">\n'
        "    <title>{subject}</title>\n"
        "</head>\n"
        "<body>\n"
        '    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">\n'
        '        <h2 style="color: #333;">您好 {username}，</h2>\n'
        "        <p>请点击以下按钮验证您的邮箱：</p>\n"
        '        <div style="text-align: center; margin: 30px 0;">\n'
        '            <a href="{verification_url}" style="background-color: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-size: 16px;">验证邮箱</a>\n'
        "        </div>\n"
        "        <p>或者复制以下链接到浏览器地址栏中访问：</p>\n"
        '        <p style="background-color: #f5f5f5; padding: 10px; border-radius: 4px; word-break: break-all;">{verification_url}</p>\n'
        "        <p><small>此链接24小时内有效。</small></p>\n"
        "        <p><small>如果您没有请求验证邮箱，请忽略此邮件。</small></p>\n"
        '<hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">\n'
        '        <p style="color: #777; font-size: 12px;">感谢使用我们的服务！<br>baykeShop团队</p>\n'
        "    </div>\n"
        "</body>\n"
        "</html>"
    ).format(
        subject=subject,
        username=user.username,
        verification_url=full_verify_url
    )

    # 异步发送邮件
    send_email_verification_task.delay(
        subject=subject,
        text_body=text_body,
        to_email=user.email,
        html_body=html_body,
        email_type='verification'
    )

    # 设置频率限制（使用配置的前缀和超时）
    cache.set(f"{email_verify_prefix}:{user.email}", 1, timeout=verify_cooldown)
    cache.set(f"{email_resend_prefix}:{user.id}", 1, timeout=resend_cooldown)

    logger.info(f"邮箱验证邮件任务已提交到队列，发送至 {user.email}")

    return {
        'success': True,
        'verify_url': full_verify_url
    }


# ============================================================
# IP可信列表管理
# ============================================================

def is_ip_trusted(bayke_user, ip_address):
    """
    检查IP是否在可信列表中（模块级函数，供Service层调用）

    Args:
        bayke_user: BaykeShopUser对象
        ip_address: 要检查的IP地址

    Returns:
        tuple: (是否可信, 错误信息)
    """
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
    """
    添加IP到可信列表

    Args:
        bayke_user: BaykeShopUser对象
        ip_address: 要添加的IP地址
    """
    try:
        trusted_ips = json.loads(bayke_user.trusted_ips)
        if ip_address not in trusted_ips:
            trusted_ips.append(ip_address)
            bayke_user.trusted_ips = json.dumps(trusted_ips)
            bayke_user.save()
    except Exception:
        # 如果解析失败，初始化为包含当前IP的列表
        bayke_user.trusted_ips = json.dumps([ip_address])
        bayke_user.save()


def clear_trusted_ips(bayke_user):
    """
    清空可信IP列表

    Args:
        bayke_user: BaykeShopUser对象
    """
    bayke_user.trusted_ips = "[]"
    bayke_user.save()


# ============================================================
# Token工具函数
# ============================================================

def generate_verification_token():
    """
    生成验证令牌

    Returns:
        str: 验证令牌
    """
    return secrets.token_urlsafe(32)


def is_verification_token_valid(bayke_user, token):
    """
    验证令牌是否匹配

    Args:
        bayke_user: BaykeShopUser对象
        token: 要验证的令牌

    Returns:
        bool: 令牌是否有效
    """
    return bayke_user.email_verification_token == token


def is_email_verification_token_valid(bayke_user):
    """
    检查邮箱验证令牌是否在有效期内

    有效期从配置读取（默认24小时）

    Args:
        bayke_user: BaykeShopUser对象

    Returns:
        bool: 令牌是否有效
    """
    from django.utils import timezone
    if not bayke_user.email_verify_at:
        return False
    expire_seconds = bayke_settings.EMAIL_VERIFY_TOKEN_EXPIRE_SECONDS
    return (timezone.now() - bayke_user.email_verify_at).total_seconds() < expire_seconds


# ============================================================
# 验证尝试次数管理
# ============================================================

def increment_verification_attempts(bayke_user):
    """
    增加验证尝试次数

    Args:
        bayke_user: BaykeShopUser对象
    """
    bayke_user.verification_attempts = bayke_user.verification_attempts + 1
    bayke_user.save()


def reset_verification_attempts(bayke_user):
    """
    重置验证尝试次数

    Args:
        bayke_user: BaykeShopUser对象
    """
    bayke_user.verification_attempts = 0
    bayke_user.save()
