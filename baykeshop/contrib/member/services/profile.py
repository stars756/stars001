import logging

from django.utils.translation import gettext_lazy as _

from baykeshop.db.security import verify_sms_code_from_request, clear_trusted_ips, record_security_operation
from baykeshop.contrib.member.models import BaykeShopUser, SecurityLog

logger = logging.getLogger("baykeshop.contrib.member")


class MemberProfileService:
    """会员资料服务"""

    @staticmethod
    def update_email(user, new_email, client_ip, request=None):
        """
        更新用户邮箱（需要SMS验证）
        """
        try:
            bayke_user = BaykeShopUser.objects.get(user=user)

            success, error_message = verify_sms_code_from_request(
                request, user.id, 'general', '验证码错误'
            )
            if not success:
                return {
                    'success': False,
                    'message': error_message,
                    'error_fields': {'sms_code': error_message}
                }

            user.email = new_email
            user.save()

            clear_trusted_ips(bayke_user)

            record_security_operation(
                bayke_user=bayke_user,
                action_type=SecurityLog.ActionTypes.CHANGE_EMAIL,
                action_detail=f"修改邮箱从 {user.email} 到 {new_email}，已清空白名单",
                ip_address=client_ip
            )

            return {'success': True}

        except Exception as e:
            logger.exception(f"Error updating email for user {user.email}: {str(e)}")
            return {'success': False}

    @staticmethod
    def update_mobile(user, new_mobile, client_ip, request=None):
        """
        更新用户手机号（需要SMS验证）
        """
        try:
            bayke_user = BaykeShopUser.objects.get(user=user)

            success, error_message = verify_sms_code_from_request(
                request, user.id, 'general', '验证码错误'
            )
            if not success:
                return {
                    'success': False,
                    'message': error_message,
                    'error_fields': {'sms_code': error_message}
                }

            old_mobile = getattr(bayke_user, 'mobile', None) or ''
            if not old_mobile:
                default_address = bayke_user.user.baykeshopuseraddress_set.filter(is_default=True).first()
                old_mobile = default_address.phone if default_address else ''

            if old_mobile == new_mobile:
                return {'success': True}

            bayke_user.mobile = new_mobile
            bayke_user.save()

            clear_trusted_ips(bayke_user)

            record_security_operation(
                bayke_user=bayke_user,
                action_type=SecurityLog.ActionTypes.CHANGE_MOBILE,
                action_detail=f"修改手机号，已清空白名单",
                ip_address=client_ip
            )

            return {'success': True}

        except Exception as e:
            logger.exception(f"Error updating mobile for user {user.email}: {str(e)}")
            return {'success': False}

    @staticmethod
    def update_profile(form, request):
        """
        统一个人资料更新入口 — 将视图层的业务逻辑收敛到 Service 层
        
        原来散落在 views/profile.py form_valid() 中的 ~24 行逻辑，
        现在统一由此方法处理，视图只负责调用和展示。
        
        Args:
            form: 已验证的 BaykeShopUserProfileForm 实例
            request: HttpRequest 对象
            
        Returns:
            dict: {'success': bool, 'errors': dict}
                 errors 的 key 是字段名（如 'email', 'mobile'），value 是错误消息
        """
        from django.contrib import messages
        
        user = request.user
        client_ip = getattr(request, '_client_ip', None)
        if not client_ip:
            from baykeshop.db.security import get_client_ip
            client_ip = get_client_ip(request)
        
        errors = {}
        
        # 邮箱更新
        email = form.cleaned_data.get('email')
        if email and email != user.email:
            result = MemberProfileService.update_email(user, email, client_ip, request)
            if not result['success']:
                errors['email'] = result.get('message', '邮箱更新失败')

        # 手机号更新
        mobile = form.cleaned_data.get('mobile')
        if mobile:
            default_addr_phone = ''
            try:
                default_addr = user.baykeshopuser.baykeshopuseraddress_set.filter(is_default=True).first()
                default_addr_phone = default_addr.phone if default_addr else ''
            except Exception:
                pass
                
            if mobile != default_addr_phone:
                result = MemberProfileService.update_mobile(user, mobile, client_ip, request)
                if not result['success']:
                    errors['mobile'] = result.get('message', '手机号更新失败')

        return {'success': len(errors) == 0, 'errors': errors}
