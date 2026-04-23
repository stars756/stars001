from django.views.generic.detail import SingleObjectMixin
from django.contrib import messages
from django.views.generic.edit import ProcessFormView
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone

from baykeshop.contrib.shop.models import BaykeShopOrders
from baykeshop.contrib.member.forms import BaykeShopOrdersCommentForm
from baykeshop.contrib.common.mixins import UserOwnedBaseView


class OrderStatusActionView(UserOwnedBaseView, SingleObjectMixin, ProcessFormView):
    """ 订单确认收货 — UserOwnedBaseView 处理用户隔离 + 未登录JSON响应 """
    model = BaykeShopOrders
    slug_field = 'order_sn'
    slug_url_kwarg = 'order_sn'
    context_object_name = 'order'

    def handle_no_permission(self):
        return JsonResponse({'code': 401, 'msg': '未登录，请登录后操作！'})

    def post(self, request, *args, **kwargs):
        order = self.get_object()
        order.status = BaykeShopOrders.OrderStatus.SIGNED
        # 先用后付：确认收货 = 付款，记录支付时间
        if order.pay_type == BaykeShopOrders.PayType.CASH and not order.pay_time:
            order.pay_time = timezone.now()
        order.save()
        messages.success(request, '确认收货成功！')
        return JsonResponse({'code': 200, 'msg': '确认收货成功！'})


class CommentActionView(OrderStatusActionView):
    """ 评论操作视图 — 继承 OrderStatusActionView 的用户隔离和权限处理"""
    model = BaykeShopOrders
    slug_field = 'order_sn'
    slug_url_kwarg = 'order_sn'
    context_object_name = 'order'

    def post(self, request, *args, **kwargs):
        order = self.get_object()
        form = BaykeShopOrdersCommentForm(request.POST)
        # 判断订单状态
        if order.status != BaykeShopOrders.OrderStatus.SIGNED:
            return JsonResponse({'code': 400, 'msg': '订单状态不正确'})

        if form.is_valid():
            new_comment = form.save(commit=False)
            new_comment.order = order
            new_comment.user = request.user
            new_comment.save()
            # 更新订单状态
            order.status = BaykeShopOrders.OrderStatus.DONE
            order.is_comment = True
            order.save()
            messages.success(request, '评论成功！')
            return HttpResponseRedirect(reverse('member:orders-list'))
        return JsonResponse({'code': 400, 'msg': '评论失败！', 'data': form.errors})
