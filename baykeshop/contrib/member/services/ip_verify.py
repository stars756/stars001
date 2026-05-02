import logging

from baykeshop.contrib.member.models import BaykeShopUser, SecurityLog
from baykeshop.db.security import add_trusted_ip, get_client_ip, is_ip_trusted

logger = logging.getLogger("baykeshop.contrib.member")


class MemberAuthService:
    """会员认证服务"""

    @staticmethod
    def authenticate_login(user, request):
        """处理登录验证逻辑"""
        try:
            bayke_user = user.baykeshopuser
            client_ip = get_client_ip(request)

            verified = bayke_user.is_email_verified
            if not verified:
                return {
                    'success': False,
                    'redirect_url': 'member:resend_verification',
                    'message': '您的邮箱尚未验证，请查收验证邮件。如未收到，可以点击重新发送。',
                    'email_resend_url': None
                }

            is_trusted, message = is_ip_trusted(bayke_user, client_ip)
            if not is_trusted:
                return {
                    'success': False,
                    'redirect_url': 'member:login',
                    'message': message
                }

            return {'success': True, 'message': f'欢迎回来，{user.username}！'}

        except BaykeShopUser.DoesNotExist:
            if user.baykeshopuser:
                bayke_user = user.baykeshopuser
                client_ip = get_client_ip(None)
                is_trusted, message = is_ip_trusted(bayke_user, client_ip)
                if not is_trusted:
                    return {'success': False, 'redirect_url': 'member:login', 'message': message}
            return {'success': True, 'message': f'欢迎回来，{user.username}！'}

    @staticmethod
    def check_email_verification(user):
        """检查用户邮箱验证状态"""
        try:
            bayke_user = user.baykeshopuser
            if not bayke_user.is_email_verified:
                return {
                    'verified': False,
                    'redirect_url': 'member:resend_verification',
                    'message': '您的邮箱尚未验证，请查收验证邮件。如未收到，可以点击重新发送。',
                }
            return {'verified': True}
        except AttributeError:
            return {'verified': False}

    @staticmethod
    def verify_ip_token(token, request):
        """
        验证IP令牌 — 将视图层 35 行业务逻辑收敛到 Service
        
        Args:
            token: IP验证令牌
            request: HttpRequest
            
        Returns:
            dict: {'success': bool, 'message': str, 'redirect_url': str}
        """
        try:
            bayke_user = BaykeShopUser.objects.get(ip_verify_token=token)

            if not bayke_user.is_ip_verify_token_valid():
                return {
                    'success': False,
                    'message': '验证链接已过期，请重新登录。',
                    'redirect_url': 'member:login'
                }

            client_ip = get_client_ip(request)
            if bayke_user.ip_verify_target != client_ip:
                return {
                    'success': False,
                    'message': 'IP地址不匹配，验证失败。',
                    'redirect_url': 'member:login'
                }

            # 执行验证通过操作
            add_trusted_ip(bayke_user, client_ip)

            # 清除一次性 token
            bayke_user.ip_verify_token = None
            bayke_user.ip_verify_at = None
            bayke_user.ip_verify_target = None
            bayke_user.save()

            # 记录安全日志
            SecurityLog.objects.create(
                user=bayke_user.user,
                ip_address=client_ip,
                action_type=SecurityLog.ActionTypes.IP_VERIFY,
                action_detail=f"IP {client_ip} 验证成功，已加入可信列表",
                status=SecurityLog.StatusChoices.SUCCESS
            )

            return {
                'success': True,
                'message': 'IP验证成功！您现在可以正常登录了。',
                'redirect_url': 'member:login'
            }

        except BaykeShopUser.DoesNotExist:
            return {
                'success': False,
                'message': '验证链接无效或已过期。',
                'redirect_url': 'member:login'
            }
