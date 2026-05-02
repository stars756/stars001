from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from baykeshop.contrib.common.mixins import UserOwnedBaseView
from baykeshop.contrib.member.forms import BaykeShopOrdersCommentForm
from baykeshop.contrib.shop.models import BaykeShopOrders


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
        context['order_timeline'] = self._build_timeline(self.object)
        return context

    def _build_timeline(self, order):
        """根据订单状态构建进度时间线"""
        s = order.OrderStatus

        # 已取消/已退款：显示终止状态
        if order.status == s.EXPIRED:
            return [
                {'label': '已下单', 'time': order.created_time, 'done': True, 'active': False},
                {'label': '已取消', 'time': order.updated_time, 'done': False, 'active': True},
            ]
        if order.status == s.REFUNDED:
            return [
                {'label': '已下单', 'time': order.created_time, 'done': True, 'active': False},
                {'label': '已支付', 'time': order.pay_time, 'done': True, 'active': False},
                {'label': '已退款', 'time': order.updated_time, 'done': False, 'active': True},
            ]

        # 虚拟商品流程
        if order.is_virtual:
            return [
                {'label': '已下单', 'time': order.created_time, 'done': True, 'active': False},
                {'label': '已支付', 'time': order.pay_time,
                 'done': order.status >= s.VERIFY, 'active': order.status == s.UNPAID and order.status != s.EXPIRED},
                {'label': '待核销', 'time': order.pay_time,
                 'done': order.status >= s.SIGNED, 'active': order.status == s.VERIFY},
                {'label': '已核销', 'time': order.verify_time or order.updated_time,
                 'done': order.status >= s.SIGNED, 'active': order.status == s.SIGNED and not order.is_comment},
                {'label': '已完成', 'time': None,
                 'done': order.status == s.DONE, 'active': order.status == s.SIGNED and order.is_comment},
            ]

        # 实物商品流程
        return [
            {'label': '已下单', 'time': order.created_time, 'done': True, 'active': False},
            {'label': '已支付', 'time': order.pay_time,
             'done': order.status >= s.PAID and order.status not in (s.EXPIRED, s.REFUNDED),
             'active': order.status == s.UNPAID},
            {'label': '已发货', 'time': order.updated_time if order.status >= s.SHIPPED else None,
             'done': order.status >= s.SHIPPED and order.status not in (s.EXPIRED, s.REFUNDED),
             'active': order.status == s.PAID},
            {'label': '已签收', 'time': order.verify_time or (order.updated_time if order.status >= s.SIGNED else None),
             'done': order.status >= s.SIGNED and order.status not in (s.EXPIRED, s.REFUNDED),
             'active': order.status == s.SHIPPED},
            {'label': '已完成', 'time': order.updated_time if order.status == s.DONE else None,
             'done': order.status == s.DONE, 'active': order.status == s.SIGNED},
        ]
