from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView
from django.utils.translation import gettext_lazy as _

from baykeshop.contrib.shop.models import BaykeShopOrders
from baykeshop.contrib.member.forms import BaykeShopOrdersCommentForm
from baykeshop.contrib.common.mixins import UserOwnedBaseView


class BaykeShopOrdersListView(UserOwnedBaseView, ListView):
    """ 订单列表 — UserOwnedBaseView 自动处理 login_url + 用户过滤 """
    template_name = 'baykeshop/member/order_list.html'
    model = BaykeShopOrders
    paginate_by = 10
    ordering = '-created_time'
    context_object_name = 'order_list'

    def get_queryset(self):
        status = self.request.GET.get('status')
        queryset = super().get_queryset()
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('我的订单')
        context['comment_form'] = BaykeShopOrdersCommentForm()
        return context


class BaykeShopOrdersDetailView(UserOwnedBaseView, DetailView):
    """ 订单详情 — UserOwnedBaseView 处理用户隔离 """
    template_name = 'baykeshop/member/order_detail.html'
    model = BaykeShopOrders
    slug_field = 'order_sn'
    slug_url_kwarg = 'order_sn'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('订单详情')
        return context
