from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse

from baykeshop.db.security import (
    get_client_ip,
    verify_user_extensions,
    check_email_verified,
    check_ip_trusted,
    check_phone_bound,
    record_security_operation,
)


class SecurityCheckBuilder:
    """
    安全检查装饰器工厂 — 组合模式

    用法示例:
        # 需要IP + 邮箱验证 + 记录日志
        @SecurityCheckBuilder.require('ip', 'email', log_type=SecurityLog.ActionTypes.CHANGE_PASSWORD)
        def my_view(request, *args, bayke_user=None, **kwargs):
            ...

        # 需要IP + 邮箱 + 手机号（不记录日志）
        @SecurityCheckBuilder.require('ip', 'email', 'phone')
        def sms_view(request, *args, bayke_user=None, **kwargs):
            ...

    支持的检查项:
        'ip'     — IP可信度检查
        'email'  — 邮箱验证检查
        'phone'  — 手机号绑定检查

    向后兼容: 原有的 sensitive_operation_required / sms_verification_required /
              email_verified_and_ip_trusted 仍可作为别名使用
    """
    # 检查项 → (检查函数, 失败消息, 是否记录到messages)
    _CHECK_REGISTRY = {
        'ip': (
            lambda request, bayke_user: (check_ip_trusted(bayke_user, get_client_ip(request))[0],
             check_ip_trusted(bayke_user, get_client_ip(request))[1]),
            '当前IP不可信，请先验证IP',
            True,
        ),
        'email': (
            lambda request, bayke_user: check_email_verified(bayke_user),
            '邮箱未验证，请先验证邮箱',
            True,
        ),
        'phone': (
            lambda request, bayke_user: check_phone_bound(bayke_user),
            '请先绑定手机号',
            True,
        ),
    }

    @classmethod
    def require(cls, *checks, log_type=None):
        """
        构建安全检查装饰器

        Args:
            *checks: 检查项列表，可选值 'ip', 'email', 'phone'
            log_type: 操作类型（SecurityLog.ActionTypes），传此参数则自动记录安全日志
        """
        def decorator(view_func):
            @wraps(view_func)
            def wrapped_view(request, *args, **kwargs):
                # 获取用户扩展信息
                bayke_user = verify_user_extensions(request)
                if not bayke_user:
                    return

                # 逐项执行检查
                for check_name in checks:
                    if check_name not in cls._CHECK_REGISTRY:
                        continue

                    check_fn, default_msg, use_messages = cls._CHECK_REGISTRY[check_name]
                    ok, msg = check_fn(request, bayke_user)

                    if not ok:
                        final_msg = msg or default_msg
                        if use_messages:
                            messages.error(request, final_msg)
                        return redirect(reverse('member:profile'))

                # 可选：记录安全日志
                if log_type:
                    record_security_operation(
                        bayke_user=bayke_user,
                        action_type=log_type,
                        action_detail=f"开始执行安全操作 {log_type}",
                        ip_address=get_client_ip(request)
                    )

                # 调用原始视图函数，注入 bayke_user 参数
                return view_func(request, *args, bayke_user=bayke_user, **kwargs)

            return wrapped_view
        return decorator


# ============================================================
# 向后兼容别名 — 保持原有导入路径可用
# 注意：当前3个装饰器均无实际使用方（死代码），
# 保留别名是为了防止将来有人通过字符串引用或动态导入
# ============================================================

def sensitive_operation_required(operation_type):
    """兼容别名：敏感操作装饰器（IP + 邮箱 + 日志）"""
    return SecurityCheckBuilder.require('ip', 'email', log_type=operation_type)


def sms_verification_required(view_func):
    """兼容别名：SMS验证装饰器（IP + 邮箱 + 手机号）"""
    return SecurityCheckBuilder.require('ip', 'email', 'phone')(view_func)


def email_verified_and_ip_trusted(view_func):
    """兼容别名：邮箱+IP验证装饰器"""
    return SecurityCheckBuilder.require('ip', 'email')(view_func)
