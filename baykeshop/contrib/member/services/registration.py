import logging
from django.db import transaction
from django.utils.translation import gettext as _

from baykeshop.db.security import get_client_ip, add_trusted_ip
from baykeshop.contrib.member.models import BaykeShopUser, BaykeShopUserAddress, SecurityLog

logger = logging.getLogger("baykeshop.contrib.member")


class MemberRegistrationService:
    """会员注册服务"""

    @staticmethod
    def register_user(form_data, request=None):
        """
        注册用户

        Args:
            form_data: 表单数据字典
            request: HttpRequest对象（可选）

        Returns:
            dict: 注册结果
        """
        try:
            with transaction.atomic():
                # 创建用户
                user = form_data.save()

                phone = form_data.cleaned_data.get("phone", "")

                # 创建BaykeShopUser，设置mobile字段
                bayke_user = BaykeShopUser.objects.create(
                    user=user,
                    nickname=form_data.cleaned_data["username"],
                    mobile=phone if phone else None  # 关键：同步手机号到mobile字段
                )

                # 添加注册IP到可信列表
                if request:
                    client_ip = get_client_ip(request)
                    if client_ip != "unknown":
                        try:
                            add_trusted_ip(bayke_user, client_ip)
                            # 记录安全日志
                            SecurityLog.objects.create(
                                user=user,
                                ip_address=client_ip,
                                action_type=SecurityLog.ActionTypes.REGISTER,
                                action_detail=f"注册成功，IP {client_ip} 已添加到可信列表",
                                status=SecurityLog.StatusChoices.SUCCESS
                            )
                        except Exception as e:
                            logger.error(f"添加可信IP失败: {str(e)}")

                # 创建默认地址
                if phone:
                    BaykeShopUserAddress.objects.create(
                        user=user,
                        name=user.username,
                        phone=phone,
                        province="",
                        city="",
                        district="",
                        address="",
                        is_default=True
                    )

                return {
                    'success': True,
                    'user': user,
                    'bayke_user': bayke_user,
                    'message': _("注册成功")
                }

        except Exception as e:
            logger.exception(f"注册失败: {str(e)}")
            return {
                'success': False,
                'message': _("注册失败，请稍后重试")
            }