from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from baykeshop.contrib.shop.services.carts_service import CartsService
from baykeshop.contrib.common.mixins import UserOwnedBaseView


class BaykeShopCartsListView(UserOwnedBaseView, ListView):
    """ 购物车列表 — UserOwnedBaseView 自动处理 login_url + 用户过滤 """
    template_name = 'baykeshop/shop/carts.html'
    context_object_name = 'carts_list'
    extra_context = {
        'title': _('购物车'),
    }

    def get_queryset(self):
        return CartsService.get_user_carts_list(self.request.user)
