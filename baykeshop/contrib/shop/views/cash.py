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
        from baykeshop.contrib.shop.views.carts import _checkout_steps
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        context['has_carts'] = self.has_carts()
        context['skus'] = queryset
        context['total'] = CashService.get_total_price(queryset)
        context['count'] = CashService.get_total_count(queryset)
        context['checkout_steps'] = _checkout_steps(1)
        return context

    def has_carts(self):
        """判断购物车是购物车商品"""
        return CashService.has_carts_from_kwargs(self.kwargs)

    def get_queryset(self):
        """获取商品数据"""
        return CashService.get_cash_queryset(self.kwargs, self.request.user)
