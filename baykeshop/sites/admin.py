from django.contrib import admin

from baykeshop.forms import ModelForm
from baykeshop.contrib.shop.services.analysis_service import (
    UserAnalysisService,
    OrderAnalysisService,
    VisitAnalysisService,
)
from baykeshop.conf import bayke_settings
from baykeshop.contrib.shop.models import BaykeShopOrders
from baykeshop.contrib.system.services.config_service import SystemConfigService
from .echarts import orders_chart, users_chart, user_pie_chart


class TabularInline(admin.TabularInline):
    """Tabular Inline View for"""
    form = ModelForm


class StackedInline(admin.StackedInline):
    """Stacked Inline View for"""
    form = ModelForm


class ModelAdmin(admin.ModelAdmin):
    """自定义ModelAdmin"""
    form = ModelForm


class AdminSite(admin.AdminSite):
    """自定义AdminSite"""

    index_template = "baykeshop/admin/index.html"

    @property
    def site_header(self):
        return SystemConfigService.get_site_header()

    @property
    def site_title(self):
        return SystemConfigService.get_site_title()

    @property
    def index_title(self):
        return SystemConfigService.get_index_title()

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        # 用户分析
        user_analysis = UserAnalysisService(request)
        user_data = user_analysis.get_data("%m-%d")
        # 订单分析
        order_analysis = OrderAnalysisService(model=BaykeShopOrders)
        # 订单销售分析
        order_data = order_analysis.get_data("%m-%d")
        sales_data = order_analysis.get_sales_data("%m-%d")
        # 访问分析
        visit_analysis = VisitAnalysisService()
        visit_data = visit_analysis.get_data("%m-%d")

        extra_context = {
            "order_data": order_data,
            "sales_data": sales_data,
            "user_data": user_data,
            "visit_data": visit_data,
            "orders_chart": orders_chart(),
            "users_chart": users_chart(),
            "user_pie_chart": user_pie_chart(),
        }
        return super().index(request, extra_context)

    def each_context(self, request):
        context = super().each_context(request)
        if bayke_settings.USE_MENU:
            context["available_apps"] = SystemConfigService.get_user_menus(
                request.user, self
            )
        return context


admin_site = AdminSite(name="baykeshop")
