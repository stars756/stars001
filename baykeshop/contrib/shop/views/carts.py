from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from baykeshop.contrib.shop.services.carts_service import CartsService
from baykeshop.contrib.common.mixins import UserOwnedBaseView


def _checkout_steps(current):
    """生成结账步骤条数据: cart, cash, pay"""
    steps = [
        {'label': _('购物车'), 'done': False, 'active': False},
        {'label': _('确认订单'), 'done': False, 'active': False},
        {'label': _('支付'), 'done': False, 'active': False},
    ]
    for i in range(current):
        steps[i]['done'] = True
    steps[current]['active'] = True
    return steps


class BaykeShopCartsListView(UserOwnedBaseView, ListView):
    """ 购物车列表 """
    template_name = 'baykeshop/shop/carts.html'
    context_object_name = 'carts_list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('购物车')
        context['checkout_steps'] = _checkout_steps(0)
        return context

    def get_queryset(self):
        return CartsService.get_user_carts_list(self.request.user)
