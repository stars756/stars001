import secrets


def generate_verification_token():
    """
    生成验证令牌

    Returns:
        str: 验证令牌
    """
    return secrets.token_urlsafe(32)
