from baykeshop.contrib.member.models import SecurityLog


def record_security_log(user, ip_address, action_type, action_detail, status=SecurityLog.StatusChoices.SUCCESS):
    """
    记录安全操作日志

    Args:
        user: 用户对象
        ip_address: 操作IP地址
        action_type: 操作类型（SecurityLog.ActionTypes）
        action_detail: 操作详情
        status: 操作状态（SecurityLog.StatusChoices）

    Returns:
        SecurityLog: 创建的安全日志对象
    """
    log = SecurityLog.objects.create(
        user=user,
        ip_address=ip_address,
        action_type=action_type,
        action_detail=action_detail,
        status=status
    )
    return log

def check_ip_verify_token_validity(bayke_user):
    """
    检查IP验证令牌是否有效（24小时有效期）

    Args:
        bayke_user: BaykeShopUser 对象

    Returns:
        bool: 令牌是否有效
    """
    return bayke_user.is_ip_verify_token_valid()
