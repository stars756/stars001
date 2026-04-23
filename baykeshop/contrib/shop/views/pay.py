from django.views.generic import DetailView, View
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse_lazy, reverse
from django.http.response import HttpResponse, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator

from baykeshop.contrib.shop.models.orders import BaykeShopOrders
from baykeshop.contrib.shop.services.pay_service import PayService
from baykeshop.contrib.common.mixins import UserOwnedBaseView


class BaykeShopOrdersPayView(UserOwnedBaseView, DetailView):
    """订单支付 — UserOwnedBaseView 自动处理 login_url + 用户过滤"""
    context_object_name = "order"
    model = BaykeShopOrders
    slug_field = "order_sn"
    slug_url_kwarg = "order_sn"
    template_name = "baykeshop/shop/pay.html"

    def get_queryset(self):
        # 支付页需要特殊查询集（包含更多字段），覆盖基类默认
        return PayService.get_user_orders_queryset(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("订单支付")
        return context


class AlipayCallBackVerifySignMixin:
    """支付宝支付回调，验签"""

    def has_verify_sign(self, data):
        """验签
        data是从请求中获得的字典数据，携带 sign和sign_type
        """
        return PayService.has_verify_sign(data)


@method_decorator(csrf_exempt, name="dispatch")
class AlipayCallbackView(AlipayCallBackVerifySignMixin, View):
    """支付宝支付结果通知"""

    def get(self, request, *args, **kwargs):
        """支付宝同步通知"""
        data = request.GET.dict()
        success = self.has_verify_sign(data)
        order_sn = data.get("out_trade_no")
        if success:
            success_processed, _ = PayService.handle_payment_success(order_sn, data)
            if not success_processed:
                pass
            return HttpResponseRedirect(
                reverse("member:orders-detail", kwargs={"order_sn": order_sn})
            )
        return HttpResponse("success")

    def post(self, request, *args, **kwargs):
        """支付宝异步通知"""
        data = request.POST.dict()
        order_sn = data.get("out_trade_no")
        success = self.has_verify_sign(data)
        if success:
            success_processed, _ = PayService.handle_payment_success(order_sn, data)
            if not success_processed:
                pass
            return HttpResponse("success")
