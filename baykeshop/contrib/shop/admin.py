import json
from django.core.cache import cache
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
from django.template.loader import render_to_string

from baykeshop.contrib.common.export import CSVExportMixin
from .models import *
from .forms import BaykeShopGoodsSKUForm

from baykeshop.contrib.shop.services.public_service import PublicService
from baykeshop.contrib.shop.services.goods_service import GoodsService
from baykeshop.sites import admin as bayke_admin

class BaykeShopCategoryInline(bayke_admin.TabularInline):
    model = BaykeShopCategory
    extra = 1


@admin.register(BaykeShopCategory)
class BaykeShopCategoryAdmin(bayke_admin.ModelAdmin):
    list_display = ["name", "parent", "order", "is_floor", "is_nav", "is_show"]
    list_editable = ["order", "is_show", "is_floor", "is_nav"]
    list_filter = [
        "is_show",
    ]
    search_fields = ["name"]
    readonly_fields = ["parent"]
    inlines = [BaykeShopCategoryInline]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "icon",
                    "order",
                    "is_floor",
                    "is_nav",
                    "is_show",
                )
            },
        ),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            kwargs["queryset"] = BaykeShopCategory.objects.filter(parent__isnull=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        if obj and obj.parent:
            return []
        return super().get_inline_instances(request, obj)

    def save_model(self, request, obj, form, change):
        """
        保存商品分类后清除缓存
        """
        super().save_model(request, obj, form, change)
        PublicService.update_goods_categories_cache()
        PublicService.update_floors_cache()

    def delete_model(self, request, obj):
        """
        删除商品分类后清除缓存
        """
        super().delete_model(request, obj)
        PublicService.update_goods_categories_cache()
        PublicService.update_floors_cache()


class BaykeShopGoodsSKUInline(bayke_admin.StackedInline):
    model = BaykeShopGoodsSKU
    extra = 1
    form = BaykeShopGoodsSKUForm
    readonly_fields = ("sales",)


class BaykeShopGoodsImagesInline(bayke_admin.TabularInline):
    model = BaykeShopGoodsImages
    extra = 1


@admin.register(BaykeShopGoods)
class BaykeShopGoodsAdmin(CSVExportMixin, bayke_admin.ModelAdmin):
    csv_fields = ['id', 'name', 'status', 'goods_type', 'is_virtual',
                  'is_recommend', 'created_time']
    csv_filename = 'goods_export.csv'
    list_display = (
        "id",
        "name",
        "image",
        "brand",
        "price",
        "sales",
        "stock",
        "is_recommend",
        "is_virtual",
        "created_time",
    )
    list_display_links = ("id", "name", "image")
    list_editable = ("is_recommend",)
    list_filter = ("category", "brand")
    search_fields = ("name", "category__name", "brand__name")
    actions = ["export_as_csv"]
    inlines = [BaykeShopGoodsSKUInline, BaykeShopGoodsImagesInline]
    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "name",
                    "category",
                    "brand"
                )
            },
        ),
        (
            _("商品详情"),
            {
                # 'classes': ('collapse',),
                "fields": (
                    "keywords",
                    "description",
                    "detail",
                    "is_virtual"
                )
            },
        ),
    )
    filter_horizontal = ("category",)

    def save_model(self, request, obj, form, change):
        """
        保存商品后清除相关缓存
        """
        super().save_model(request, obj, form, change)
        # 清除商品SPU详情缓存
        GoodsService.update_goods_spu_detail_cache(obj.id)
        # 清除首页楼层缓存（商品变更影响楼层展示）
        PublicService.update_floors_cache()
        # 清除所有SKU详情缓存
        for sku in obj.baykeshopgoodssku_set.all():
            GoodsService.update_goods_detail_cache(sku.id)

    def delete_model(self, request, obj):
        """
        删除商品后清除相关缓存
        """
        # 先获取SKU IDs用于清除缓存
        sku_ids = list(obj.baykeshopgoodssku_set.values_list('id', flat=True))
        super().delete_model(request, obj)
        # 清除商品SPU详情缓存
        GoodsService.update_goods_spu_detail_cache(obj.id)
        # 清除首页楼层缓存
        PublicService.update_floors_cache()
        # 清除所有SKU详情缓存
        for sku_id in sku_ids:
            GoodsService.update_goods_detail_cache(sku_id)

    @admin.display(description="商品价格")
    def price(self, obj):
        if obj.price:
            return round(obj.price, 2)
        return None

    @admin.display(description="商品销量")
    def sales(self, obj):
        return obj.sales

    @admin.display(description="商品库存")
    def stock(self, obj):
        return obj.stock

    @admin.display(description="商品图片")
    def image(self, obj):
        return format_html(
            '<img src="/media/{}" width="64" height="64" />', obj.image_url
        )


@admin.register(BaykeShopBrand)
class BaykeShopBrandAdmin(bayke_admin.ModelAdmin):
    """Admin View for BaykeShopBrand"""

    list_display = ("id", "name", "image", "order", "created_time")
    list_display_links = ("id", "name")
    search_fields = ("name", "description")
    list_editable = ("order",)

    fieldsets = (
        (_("基本信息"), {"fields": ("image", "name", "description", "order")}),
    )


class BaykeShopOrdersGoodsInline(bayke_admin.TabularInline):
    model = BaykeShopOrdersGoods
    extra = 0
    exclude = ("specs", "sku", "detail", "image")
    readonly_fields = ("_image", "name", "price", "quantity", "_specs", "sku_sn")

    @admin.display(description="规格")
    def _specs(self, obj):
        specs = obj.specs
        if isinstance(specs, str):
            specs = json.loads(obj.specs)
        if not specs:
            return "-"
        return ", ".join([f"{spec['parent__name']}:{spec['name']}" for spec in specs])

    @admin.display(description="商品图片")
    def _image(self, obj):
        if not obj.image:
            return "-"
        return format_html('<img src="/media/{}" width="64" height="64" />', obj.image)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BaykeShopOrders)
class BaykeShopOrdersAdmin(CSVExportMixin, bayke_admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "order_sn",
        "order_skus",
        "status",
        "pay_type",
        "pay_price",
        "carrier",
        "tracking_number",
        "is_verify",
        "is_comment",
        "created_time",
        "pay_time",
    )
    list_display_links = ("id", "user", "order_sn")
    list_editable = ("carrier", "tracking_number")
    search_fields = ("id", "user__username", "user__nickname", "tracking_number")
    list_filter = ("status", "pay_type", "is_verify", "is_comment")
    readonly_fields = (
        "order_sn",
        "user",
        "pay_type",
        "is_comment",
        "pay_sn",
        "pay_time",
        "is_verify",
        "verify_time",
    )
    inlines = [
        BaykeShopOrdersGoodsInline,
    ]
    csv_fields = ['id', 'user', 'order_sn', 'status', 'pay_price',
                  'pay_type', 'carrier', 'tracking_number',
                  'cancel_reason', 'receiver', 'phone', 'address',
                  'created_time', 'pay_time', 'pay_sn']
    csv_filename = 'orders_export.csv'
    actions = ["shipments", "verify", "refund", "export_as_csv"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in [0, 1]:
            return super().has_change_permission(request, obj)
        return False

    @admin.display(description="订单商品")
    def order_skus(self, obj):
        queryset = obj.baykeshopordersgoods_set.all()
        return render_to_string(
            "baykeshop/admin/ordersgoods.html", {"queryset": queryset}
        )

    @admin.action(description="所选订单 发货")
    def shipments(self, request, queryset):
        for item in queryset:
            if item.status != BaykeShopOrders.OrderStatus.PAID:
                continue
            item.status = BaykeShopOrders.OrderStatus.SHIPPED
            item.save()
        self.message_user(request, "发货成功")

    @admin.action(description="所选订单 核销")
    def verify(self, request, queryset):
        for item in queryset:
            if item.status != BaykeShopOrders.OrderStatus.VERIFY:
                continue
            item.status = BaykeShopOrders.OrderStatus.SIGNED
            item.is_verify = True
            item.pay_time = timezone.now()
            item.save()
        self.message_user(request, "核销成功")

    @admin.action(description="所选订单 退款（恢复库存+回滚销量）")
    def refund(self, request, queryset):
        """退款操作 — pre_save 信号自动触发 apply_status_transition 恢复库存/销量"""
        refundable = [
            BaykeShopOrders.OrderStatus.PAID,
            BaykeShopOrders.OrderStatus.SHIPPED,
            BaykeShopOrders.OrderStatus.SIGNED,
        ]
        count = 0
        for item in queryset:
            if item.status not in refundable:
                continue
            item.status = BaykeShopOrders.OrderStatus.REFUNDED
            item.save()
            count += 1
        self.message_user(request, f"已退款 {count} 个订单，库存和销量已自动恢复")


# 规格值
class BaykeShopSpecInline(bayke_admin.TabularInline):
    model = BaykeShopSpec
    extra = 1
    verbose_name = _("规格值")
    verbose_name_plural = _("规格值")


@admin.register(BaykeShopSpec)
class BaykeShopSpecAdmin(bayke_admin.ModelAdmin):
    """Admin View for BaykeShopSpec"""

    list_display = ("id", "name", "parent", "order", "is_show", "created_time")
    list_display_links = ("id", "name")
    search_fields = ("name",)

    fieldsets = ((_("规格名称"), {"fields": ("name", "order", "is_show")}),)
    readonly_fields = ("parent",)
    inlines = [BaykeShopSpecInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            kwargs["queryset"] = BaykeShopSpec.objects.filter(parent__isnull=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        if obj and obj.parent:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(BaykeShopOrdersComment)
class BaykeShopOrdersCommentAdmin(bayke_admin.ModelAdmin):
    """Admin View for BaykeShopOrdersComment"""

    list_display = (
        "id",
        "user",
        "order",
        "score",
        "content",
        "reply_user",
        "status",
        "created_time",
    )
    list_display_links = ("id", "user", "order")
    list_editable = ("status",)
    search_fields = ("user__username", "user__nickname")
    list_filter = ("score",)
    readonly_fields = ("user", "order", "content", "reply_user", "score")

    fieldsets = (
        (_("评论信息"), {"fields": ("user", "order", "content", "score")}),
        (_("回复信息"), {"fields": ("reply_user", "reply_content", "status")}),
    )

    def _invalidate_comment_cache(self, comment):
        """清除评论关联商品（SPU）的评分缓存"""
        order_good = comment.order.baykeshopordersgoods_set.first()
        if order_good and order_good.sku:
            from baykeshop.contrib.shop.services.comment_service import CommentService
            spu_id = order_good.sku.goods_id
            cache.delete_many([
                CommentService._cache_key(spu_id, 'avg'),
                CommentService._cache_key(spu_id, 'count'),
                CommentService._cache_key(spu_id, 'rate'),
            ])

    def save_model(self, request, obj, form, change):
        obj.reply_user = request.user
        result = super().save_model(request, obj, form, change)
        self._invalidate_comment_cache(obj)
        return result

    def delete_model(self, request, obj):
        self._invalidate_comment_cache(obj)
        return super().delete_model(request, obj)

    def has_add_permission(self, request, obj=None):
        return False
