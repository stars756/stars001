import random

from django.core.cache import cache

from baykeshop.conf import bayke_settings

from .security_log import security_logger


def get_sms_cache_key(user_id, operation_type):
    """获取SMS验证码的Redis缓存键"""
    prefix = bayke_settings.CACHE_PREFIX_SMS_VERIFY
    return f"{prefix}:{user_id}:{operation_type}"


def get_sms_minute_rate_key(user_id, operation_type):
    """获取1分钟限流键"""
    prefix = bayke_settings.CACHE_PREFIX_SMS_RATE_MINUTE
    return f"{prefix}:{user_id}:{operation_type}"


def get_sms_hour_rate_key(user_id, operation_type):
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
        operation_type: 操作类型

    Returns:
        str: Redis缓存键
    """
    cache_key = get_sms_cache_key(user_id, operation_type)
    expire_seconds = bayke_settings.SMS_CODE_EXPIRE_SECONDS
    cache.set(cache_key, code, expire_seconds)
    return cache_key


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
    minute_key = get_sms_minute_rate_key(user_id, operation_type)
    hour_key = get_sms_hour_rate_key(user_id, operation_type)

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
    增加SMS发送计数（原子操作，防并发竞态）

    使用 cache.incr() 替代 get/set，避免 read-then-write 竞态。
    注意：incr 不重置 TTL，窗口时间从首次 set 起算。
    依赖 Redis 后端（LocMemCache 不支持 incr）。

    Args:
        user_id: 用户ID
        operation_type: 操作类型
    """
    minute_key = get_sms_minute_rate_key(user_id, operation_type)
    hour_key = get_sms_hour_rate_key(user_id, operation_type)

    minute_window = bayke_settings.SMS_RATE_MINUTE_WINDOW
    hour_window = bayke_settings.SMS_RATE_HOUR_WINDOW

    try:
        cache.incr(minute_key)
    except ValueError:
        cache.set(minute_key, 1, timeout=minute_window)

    try:
        cache.incr(hour_key)
    except ValueError:
        cache.set(hour_key, 1, timeout=hour_window)
