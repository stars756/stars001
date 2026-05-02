import logging

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from baykeshop.conf import bayke_settings
from baykeshop.contrib.member.models import BaykeShopUser
from baykeshop.db.security import (
    generate_verification_token,
    get_client_ip,
    is_email_verification_token_valid,
    is_verification_token_valid,
    send_verification_email_to_user,
)

logger = logging.getLogger("baykeshop.contrib.member")


class MemberEmailService:
    """会员邮件服务"""

    @staticmethod
    def send_verification_email(user, bayke_user, request=None):
        """
        发送邮箱验证邮件

        Args:
            user: 用户对象
            bayke_user: 会员扩展用户对象
            request: HttpRequest对象（可选）

        Returns:
            dict: 包含是否发送成功
        """
        logger.info("=== 开始发送验证邮件 ===")
        logger.info(f"用户: {user.username}, 邮箱: {user.email}")

        client_ip = get_client_ip(request) if request else "unknown"
        result = send_verification_email_to_user(user, request, client_ip, bayke_user)
        logger.info("已更新发送时间")

        # 使用配置化的缓存键和超时
        email_verify_prefix = bayke_settings.CACHE_PREFIX_EMAIL_VERIFY_LIMIT
        email_resend_prefix = bayke_settings.CACHE_PREFIX_EMAIL_RESEND_LIMIT
        verify_cooldown = bayke_settings.EMAIL_VERIFY_COOLDOWN_SECONDS

        cache.set(f"{email_verify_prefix}:{user.email}", 1, timeout=verify_cooldown)

        # resend 方法中的频率限制也使用配置值
        cache.set(f"{email_resend_prefix}:{user.id}", 1, timeout=bayke_settings.EMAIL_RESEND_COOLDOWN_SECONDS)

        logger.info("邮件发送任务已提交到队列")
        return result

    @staticmethod
    def resend_verification_email(user, request=None):
        """
        重新发送验证邮件

        Args:
            user: 用户对象
            request: HttpRequest对象（可选）

        Returns:
            dict: 包含是否成功、错误信息等
        """
        try:
            from django.conf import settings as django_settings
            from django.utils.translation import gettext as _

            from baykeshop.contrib.member.tasks import send_email_task

            bayke_user = user.baykeshopuser

            if bayke_user.is_email_verified:
                return {
                    'success': True,
                    'message': '您的邮箱已经验证过了。',
                    'redirect_url': reverse('member:profile')
                }

            resend_limit_key = f"{bayke_settings.CACHE_PREFIX_EMAIL_RESEND_LIMIT}:{user.id}"
            if cache.get(resend_limit_key):
                return {
                    'success': False,
                    'message': '发送过于频繁，请稍后再试',
                    'redirect_url': reverse('member:profile')
                }

            token = generate_verification_token()
            bayke_user.email_verification_token = token
            bayke_user.email_verify_at = timezone.now()
            bayke_user.save()

            # 构建验证 URL 并异步发送邮件（修复：原来缺少此步骤）
            verify_url = reverse("member:verify_email", kwargs={"token": token})
            full_verify_url = ""
            if request:
                full_verify_url = request.build_absolute_uri(verify_url)

            email_subject_prefix = getattr(django_settings, 'EMAIL_SUBJECT_PREFIX', '[baykeShop]')
            subject = f"{email_subject_prefix}{_('邮箱验证')}"

            text_body = _(
                "您好 {username}，\n\n"
                "请点击以下链接验证您的邮箱：\n"
                "{verification_url}\n\n"
                "如果链接无法点击，请复制链接到浏览器地址栏中访问。\n"
                "此链接24小时内有效。\n\n"
                "如果您没有请求验证邮箱，请忽略此邮件。\n\n"
                "感谢使用我们的服务！\n"
                "baykeShop团队"
            ).format(username=user.username, verification_url=full_verify_url)

            # 异步提交到 Celery 队列
            send_email_task.delay(
                subject=subject,
                text_body=text_body,
                to_email=user.email,
                email_type='verification'
            )

            cache.set(resend_limit_key, 1, timeout=300)

            logger.info(f"[重发] 验证邮件任务已提交到队列 - 用户: {user.username}, 收件人: {user.email}")

            return {
                'success': True,
                'message': '验证邮件已发送，请查收。',
                'redirect_url': reverse('member:profile')
            }

        except Exception as e:
            logger.exception(f"Error resending verification email for user {user.username}: {str(e)}")
            return {
                'success': False,
                'message': '发送验证邮件失败，请稍后再试',
                'redirect_url': reverse('member:profile')
            }


class MemberVerificationService:
    """会员验证服务"""

    @staticmethod
    def verify_email(token):
        """
        验证邮箱

        Args:
            token: 验证令牌

        Returns:
            dict: 包含验证结果
        """
        try:
            logger.info("=== 开始验证邮箱 ===")
            logger.info(f"Token: {token}")

            try:
                logger.info(f"正在查找邮箱验证令牌为 '{token}' 的用户...")
                bayke_user = BaykeShopUser.objects.get(email_verification_token=token)
                logger.info(f"找到用户: {bayke_user.user.username}")
                logger.info(f"当前 token: {bayke_user.email_verification_token}")
            except BaykeShopUser.DoesNotExist:
                logger.warning(f"未找到邮箱验证令牌为 '{token}' 的用户")
                all_users = list(BaykeShopUser.objects.values_list('email_verification_token', 'user__username'))
                logger.warning(f"数据库中所有 token: {all_users}")
                return {
                    'success': False,
                    'message': '验证链接无效或已过期。',
                    'redirect_url': reverse('member:register')
                }

            if bayke_user.is_email_verified:
                logger.warning(f"用户 {bayke_user.user.username} 已经验证过邮箱")
                return {
                    'success': False,
                    'message': '您的邮箱已经验证过了。',
                    'redirect_url': reverse('member:register')
                }

            logger.info("验证 token 完整性...")
            if not is_verification_token_valid(bayke_user, token):
                logger.warning("Token 完整性验证失败")
                return {
                    'success': False,
                    'message': "验证链接无效，请重新获取",
                    'redirect_url': reverse('member:register')
                }

            logger.info("检查令牌是否过期...")
            if not is_email_verification_token_valid(bayke_user):
                logger.warning("Token 已过期")
                return {
                    'success': False,
                    'message': "验证链接已过期，请重新发送",
                    'redirect_url': reverse('member:register')
                }

            logger.info("开始验证邮箱...")
            bayke_user.is_email_verified = True
            bayke_user.email_verified_at = timezone.now()
            bayke_user.email_verification_token = None
            bayke_user.save()

            logger.info(f"Email verification successful for user: {bayke_user.user.username}")
            return {
                'success': True,
                'message': '邮箱验证成功！请登录您的账号。',
                'redirect_url': reverse('member:login')
            }

        except Exception as e:
            logger.exception(f"Error during email verification: {str(e)}")
            return {
                'success': False,
                'message': '验证过程中发生错误，请重试或联系客服。',
                'redirect_url': reverse('member:register')
            }
