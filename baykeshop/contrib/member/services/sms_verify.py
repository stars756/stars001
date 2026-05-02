import logging

from baykeshop.contrib.member.tasks import send_sms_verify_task
from baykeshop.db.security import (
    cache_sms_code,
    check_sms_rate_limit,
    generate_sms_code,
    get_client_ip,
    increment_sms_rate_limit,
    is_ip_trusted,
)

logger = logging.getLogger("baykeshop.contrib.member")


class MemberSMSAuthService:
    """会员短信验证服务"""

    @staticmethod
    def send_verification_code(user, request=None, operation_type="general"):
        """
        发送SMS验证码

        Args:
            user: 用户对象
            request: HttpRequest对象（可选，用于获取客户端IP）
            operation_type: 操作类型，用于区分不同场景的验证码（如'general'、'change_email'、'change_mobile'等）

        Returns:
            dict: 包含发送结果和错误信息
        """
        try:
            bayke_user = user.baykeshopuser
            client_ip = get_client_ip(request)

            is_trusted, message = is_ip_trusted(bayke_user, client_ip)
            if not is_trusted:
                logger.warning(f"IP验证失败 - 用户: {user.id}, IP: {client_ip}, 原因: {message}")
                return {
                    'success': False,
                    'message': message,
                    'redirect_url': 'member:profile'
                }

            if not bayke_user.is_email_verified:
                logger.warning(f"邮箱未验证 - 用户: {user.id}, 邮箱: {user.email}")
                return {
                    'success': False,
                    'message': "邮箱未验证，请先验证邮箱",
                    'redirect_url': 'member:profile'
                }

            # 检查手机号：优先检查bayke_user.mobile，其次检查默认地址中的手机号
            has_mobile = bool(bayke_user.mobile) or bayke_user.user.baykeshopuseraddress_set.filter(is_default=True).exists()
            if not has_mobile:
                logger.warning(f"未绑定手机号 - 用户: {user.id}, mobile字段: {bayke_user.mobile}")
                return {
                    'success': False,
                    'message': "请先绑定或设置手机号",
                    'redirect_url': 'member:profile'
                }

            can_send, limit_message = check_sms_rate_limit(bayke_user.user.id, operation_type)
            if not can_send:
                logger.info(f"频率限制 - 用户: {user.id}, 操作类型: {operation_type}, 限制原因: {limit_message}")
                return {
                    'success': False,
                    'message': limit_message,
                    'redirect_url': 'member:profile'
                }

            code = generate_sms_code()

            # 获取手机号：优先使用bayke_user.mobile，其次使用默认地址中的手机号
            phone_number = None
            if bayke_user.mobile:
                phone_number = bayke_user.mobile
            else:
                default_address = bayke_user.user.baykeshopuseraddress_set.filter(is_default=True).first()
                if default_address:
                    phone_number = default_address.phone

            if not phone_number:
                logger.error(f"无法获取手机号 - 用户: {user.id}")
                return {
                    'success': False,
                    'message': "无法获取手机号，请联系客服",
                    'redirect_url': 'member:profile'
                }

            cache_sms_code(bayke_user.user.id, code, operation_type)
            increment_sms_rate_limit(bayke_user.user.id, operation_type)

            send_sms_verify_task.delay(
                user_id=bayke_user.user.id,
                phone_number=phone_number,
                code=code,
                operation_type=operation_type,
                message=f"您的验证码是：{code}"
            )

            logger.info(f"短信验证码发送成功 - 用户: {user.id}, 操作类型: {operation_type}, 手机号: {phone_number}, 验证码: {code}")

            return {
                'success': True,
                'message': '验证码已发送，请查收短信。',
                'redirect_url': 'member:profile'
            }

        except Exception as e:
            logger.exception(f"Error sending SMS verification code: {str(e)}")
            return {
                'success': False,
                'message': f"发送验证码失败：{str(e)}",
                'redirect_url': 'member:profile'
            }

    @staticmethod
    def verify_code(user, code, operation_type='general'):
        """
        验证SMS验证码（补全原Service层缺失的验证方法）

        Args:
            user: 用户对象
            code: 用户输入的验证码
            operation_type: 操作类型

        Returns:
            dict: {'success': bool, 'message': str}
        """
        try:
            from baykeshop.db.security import verify_sms_code
            is_valid = verify_sms_code(user.id, code, operation_type)
            if is_valid:
                return {
                    'success': True,
                    'message': '验证码正确'
                }
            return {
                'success': False,
                'message': '验证码错误或已过期'
            }
        except Exception as e:
            logger.exception(f"Error verifying SMS code for user {user.id}: {str(e)}")
            return {
                'success': False,
                'message': '验证失败，请重试'
            }
