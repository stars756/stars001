from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from baykeshop.contrib.shop.services.cash_service import CashService
from baykeshop.contrib.common.mixins import BaykeLoginRequiredMixin


class BaykeShopCashView(BaykeLoginRequiredMixin, TemplateView):
    """收银台视图 — 使用统一的 BaykeLoginRequiredMixin（自动带消息提示）"""
    template_name = 'baykeshop/shop/cash.html'
    extra_context = {
        'title': '收银台',
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['has_carts'] = self.has_carts()
        context['skus'] = self.get_queryset()
        context['total'] = self.get_total_price()
        context['count'] = self.get_total_count()
        return context

    def has_carts(self):
        """判断购物车是购物车商品"""
        return CashService.has_carts_from_kwargs(self.kwargs)

    def get_queryset(self):
        """获取商品数据"""
        return CashService.get_cash_queryset(self.kwargs, self.request.user)

    def get_total_price(self):
        return CashService.get_total_price(self.get_queryset())

    def get_total_count(self):
        return CashService.get_total_count(self.get_queryset())
