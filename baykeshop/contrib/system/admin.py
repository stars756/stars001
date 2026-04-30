from django.contrib import admin
from django.contrib.sites.models import Site
from django.contrib.sites.admin import SiteAdmin
from django.contrib.auth.models import Permission
from django.utils.translation import gettext_lazy as _
from baykeshop.sites import admin as bayke_admin

from baykeshop.conf import bayke_settings
from .models import *
from baykeshop.contrib.shop.services.public_service import PublicService

admin.site.unregister(Site)

@admin.register(Site)
class BaykeSiteAdmin(SiteAdmin):
    list_display = (
        "domain",
        "name",
    )
    search_fields = ("domain", "name")
    fieldsets = ((None, {"fields": ("domain", "name")}),)

    def has_add_permission(self, request):
        return False


@admin.register(BaykeDictModel)
class BaykeDictModelAdmin(bayke_admin.ModelAdmin):
    list_display = ("key", "name", "created_time")
    search_fields = ("key", "name", "value")
    fieldsets = ((None, {"fields": ("key", "name", "value")}),)

    def get_readonly_fields(self, request, obj=None):
        if obj and hasattr(bayke_settings, obj.key):
            return ["key"]
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and hasattr(bayke_settings, obj.key):
            self.message_user(request, _(f"{obj.key}为系统内置字典不允许删除"), "WARNING")
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from django.core.cache import cache
        cache.delete(f"dict:value:{obj.key}")

    def delete_model(self, request, obj):
        from django.core.cache import cache
        cache.delete(f"dict:value:{obj.key}")
        super().delete_model(request, obj)


@admin.register(BaykeBanners)
class BaykeBannersAdmin(bayke_admin.ModelAdmin):
    list_display = ("title", "image", "url", "is_show", "order", "created_time")
    search_fields = ("title", "url")
    fieldsets = ((None, {"fields": ("title", "image", "url", "is_show", "order")}),)

    def save_model(self, request, obj, form, change):
        """
        保存轮播图后清除缓存
        """
        super().save_model(request, obj, form, change)
        PublicService.update_banners_cache()

    def delete_model(self, request, obj):
        """
        删除轮播图后清除缓存
        """
        super().delete_model(request, obj)
        PublicService.update_banners_cache()


class BaykeMenuInline(bayke_admin.TabularInline):
    model = BaykeMenus
    extra = 1
    autocomplete_fields = ("permission",)
    

@admin.register(Permission)
class PermissionAdmin(bayke_admin.ModelAdmin):
    list_display = ("name", "codename")
    search_fields = ("name", "codename")
    fieldsets = (
        (None, {"fields": ("name", "codename")}),
    )


@admin.register(BaykeMenus)
class BaykeMenusAdmin(bayke_admin.ModelAdmin):
    list_display = ("name", "parent", "icon", "is_show", "order", "created_time")
    search_fields = ("name",)
    list_editable = ("is_show", "order")
    fields = ("name", "icon", "is_show", "order",)
    readonly_fields = ("parent", "permission")
    list_select_related = ("permission",)
    autocomplete_fields = ("permission",)
    inlines = (BaykeMenuInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            kwargs["queryset"] = BaykeMenus.objects.filter(parent__isnull=True, is_show=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def get_inlines(self, request, obj):
        """ 禁用子菜单 """
        if obj and obj.parent:
            return []
        return super().get_inlines(request, obj)
    
    def get_readonly_fields(self, request, obj=None):
        """ 禁用子菜单 """
        if obj and obj.parent:
            return []
        return super().get_readonly_fields(request, obj)
    
    def get_fields(self, request, obj=None):
        """ 编辑子菜单时允许修改父类和权限标识 """
        if obj and obj.parent:
            return ("name", "icon", "parent", "permission", "order", "is_show")
        return super().get_fields(request, obj)
    