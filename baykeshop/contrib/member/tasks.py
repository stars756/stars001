import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from baykeshop.contrib.system.models import BaykeDictModel

logger = logging.getLogger("baykeshop.contrib.member")


def _build_email_connection():
    """
    构建邮件连接（公共方法，从系统配置读取）

    Returns:
        connection: Django邮件连接对象
        from_email: 发件人地址
    """
    from_email = BaykeDictModel.get_key_value("EMAIL_HOST_USER")
    email_host = BaykeDictModel.get_key_value("EMAIL_HOST")
    email_port = int(BaykeDictModel.get_key_value("EMAIL_PORT"))
    email_username = BaykeDictModel.get_key_value("EMAIL_HOST_USER")
    email_password = BaykeDictModel.get_key_value("EMAIL_HOST_PASSWORD")
    email_use_ssl = BaykeDictModel.get_key_value("EMAIL_USE_SSL")

    # 邮件后端选择：开发环境用控制台，生产环境用SMTP
    DEVELOP_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    PRODUCTION_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    backend = PRODUCTION_EMAIL_BACKEND if not settings.DEBUG else DEVELOP_EMAIL_BACKEND

    connection = get_connection(
        fail_silently=False,
        host=email_host,
        port=email_port,
        username=email_username,
        password=email_password,
        use_ssl=email_use_ssl,
        from_email=from_email,
        backend=backend,
    )
    return connection, from_email


@shared_task(bind=True, max_retries=3)
def send_email_task(
    self,
    subject: str,
    text_body: str,
    to_email: str,
    html_body: str = None,
    email_type: str = 'general'
):
    """
    通用异步邮件发送任务（统一替代原来的3个独立任务）

    Args:
        self: Celery task bind instance
        subject: 邮件主题
        text_body: 纯文本内容
        to_email: 收件人邮箱
        html_body: HTML内容（可选）
        email_type: 邮件类型标识，用于日志区分 ('verification' | 'password_reset' | 'ip_verify' | 'general')
    """
    try:
        connection, from_email = _build_email_connection()

        # 构建邮件对象
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[to_email],
            connection=connection
        )

        # 附加HTML邮件内容
        if html_body:
            email_message.attach_alternative(html_body, "text/html")

        # 执行发送
        email_message.send()
        logger.info(f"[{email_type}] 邮件已成功发送至 {to_email}")

    except Exception as e:
        logger.exception(f"发送邮件至 {to_email} 失败 [{email_type}]，错误：{str(e)}")
        # 失败自动重试，最多3次，每次间隔60秒
        raise self.retry(exc=e, countdown=60)


# ============================================================
# 向后兼容别名 — 保持原有调用方无需改动
# 原来的3个函数签名完全一致，直接指向 send_email_task 即可
# ============================================================

# 邮箱验证邮件（被 db/security.py 调用）
send_email_verification_task = send_email_task

# 密码重置邮件（被 forms/auth.py 调用）
send_reset_password_email_task = send_email_task

# IP验证邮件（当前未被调用，保留别名以备将来使用）
send_ip_verify_email_task = send_email_task


@shared_task(bind=True, max_retries=3)
def send_sms_verify_task(
    self,
    user_id: int,
    phone_number: str,
    code: str,
    operation_type: str,
    message: str = None
):
    """
    异步发送SMS验证码任务
    Demo阶段打印到控制台，生产环境替换为短信SDK
    """
    try:
        # Demo阶段：打印到控制台
        if settings.DEBUG:
            print("=== SMS验证码发送 (Demo模式) ===")
            print(f"用户ID: {user_id}")
            print(f"手机号: {phone_number}")
            print(f"验证码: {code}")
            print(f"操作类型: {operation_type}")
            print(f"消息: {message or '请使用验证码进行验证'}")
            print("=" * 40)
            logger.info(f"短信验证码已发送（Demo模式）- 用户ID: {user_id}, 手机号: {phone_number}, 操作类型: {operation_type}")
            return

        # 生产环境：集成短信SDK
        # 这里预留短信SDK集成位置
        logger.warning(f"短信SDK未集成 - 用户ID: {user_id}, 手机号: {phone_number}, 操作类型: {operation_type}")
        # from some_sms_sdk import send_sms
        # send_sms(phone_number, message or f"您的验证码是：{code}")
        logger.info(f"短信验证码发送完成 - 用户ID: {user_id}, 手机号: {phone_number}, 操作类型: {operation_type}")

    except Exception as e:
        logger.exception(f"发送短信验证码失败 - 用户ID: {user_id}, 手机号: {phone_number}, 操作类型: {operation_type}, 错误: {str(e)}")
        # 失败自动重试，最多3次，每次间隔60秒
        raise self.retry(exc=e, countdown=60)
