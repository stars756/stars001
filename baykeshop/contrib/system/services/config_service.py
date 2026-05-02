import json
import logging

from baykeshop.contrib.system.models import BaykeDictModel, BaykeMenus
from baykeshop.contrib.system.validators import is_bool, is_dict, is_json, is_list

logger = logging.getLogger("baykeshop.contrib.system")


class SystemConfigService:
    """系统配置服务 — 统一的字典/Menu/轮播配置读取入口"""

    # 常用配置键
    KEY_SITE_HEADER = "SITE_HEADER"
    KEY_SITE_TITLE = "SITE_TITLE"
    KEY_INDEX_TITLE = "INDEX_TITLE"

    @staticmethod
    def get_config(key, default=None):
        """
        读取字典配置值（类型自动解析）

        支持类型：bool / dict / list / json / 纯文本
        数据库异常时返回 default 而非抛出异常。
        """
        try:
            obj = BaykeDictModel.current_site.get(key=key)
            value = obj.value
            if is_bool(value):
                return json.loads(value.lower())
            if is_dict(value):
                return {
                    k: v
                    for item in value.splitlines()
                    for k, v in [item.split(':', 1)]
                }
            if is_list(value):
                lines = value.splitlines()
                return lines if len(lines) > 1 else value
            if is_json(value):
                return json.loads(value)
        except Exception as e:
            logger.warning(f"读取配置 {key} 失败: {e}")
        return default

    @staticmethod
    def get_site_header():
        return SystemConfigService.get_config(SystemConfigService.KEY_SITE_HEADER)

    @staticmethod
    def get_site_title():
        return SystemConfigService.get_config(SystemConfigService.KEY_SITE_TITLE)

    @staticmethod
    def get_index_title():
        return SystemConfigService.get_config(SystemConfigService.KEY_INDEX_TITLE)

    @staticmethod
    def get_alipay_app_id():
        """支付宝 APPID（Sandbox 模式下自动切换）"""
        from django.conf import settings
        key = "ALIPAY_SANDBOX_APPID" if settings.DEBUG else "ALIPAY_APPID"
        return SystemConfigService.get_config(key)

    @staticmethod
    def get_alipay_keys():
        """获取支付宝公私钥"""
        from django.conf import settings
        if settings.DEBUG:
            return (
                SystemConfigService.get_config("ALIPAY_SANDBOX_PRIVATE_KEY"),
                SystemConfigService.get_config("ALIPAY_SANDBOX_PUBLIC_KEY"),
            )
        return (
            SystemConfigService.get_config("ALIPAY_PRIVATE_KEY"),
            SystemConfigService.get_config("ALIPAY_PUBLIC_KEY"),
        )

    # ============================================================
    # 菜单服务
    # ============================================================

    @staticmethod
    def get_user_menus(user, admin_site):
        """
        根据用户权限构建 Admin 菜单树

        Args:
            user: User 对象
            admin_site: AdminSite 实例（用于 is_registered / _registry 查询）

        返回格式：[{name, icon, order, models: [{name, icon, ...}]}, ...]
        """
        from django.urls import NoReverseMatch, reverse

        perms = user.get_all_permissions()
        parent_groups = {}

        for perm in perms:
            app_label, codename = perm.split('.')
            menus = BaykeMenus.objects.filter(
                permission__content_type__app_label=app_label,
                permission__codename=codename,
                parent__isnull=False,
                is_show=True,
            ).select_related('parent', 'permission__content_type')

            for menu in menus:
                model = menu.permission.content_type.model_class()
                if not model:
                    continue
                if not admin_site.is_registered(model):
                    continue

                model_admin = admin_site._registry[model]
                model_perms = model_admin.get_model_perms(user)

                if menu.parent not in parent_groups:
                    parent_groups[menu.parent] = []

                item = {
                    "name": menu.name,
                    "icon": menu.icon,
                    "order": menu.order,
                    "model": model,
                    "perms": model_perms,
                    "object_name": model._meta.object_name,
                }

                if model_perms.get("change") or model_perms.get("view"):
                    item["view_only"] = not model_perms.get("change")
                    try:
                        item["admin_url"] = reverse(
                            f"admin:{app_label}_{model._meta.model_name}_changelist",
                            current_app=admin_site.name,
                        )
                    except NoReverseMatch:
                        pass

                if model_perms.get("add"):
                    try:
                        item["add_url"] = reverse(
                            f"admin:{app_label}_{model._meta.model_name}_add",
                            current_app=admin_site.name,
                        )
                    except NoReverseMatch:
                        pass

                parent_groups[menu.parent].append(item)

        result = []
        for parent, models in parent_groups.items():
            result.append({
                "name": parent.name,
                "icon": parent.icon,
                "order": parent.order,
                "models": sorted(models, key=lambda x: x["order"]),
            })

        return sorted(result, key=lambda x: x["order"])


config_service = SystemConfigService()
