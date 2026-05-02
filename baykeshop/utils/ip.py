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
