import logging

from django.http.response import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, View

from baykeshop.contrib.common.mixins import UserOwnedBaseView
from baykeshop.contrib.shop.models.orders import BaykeShopOrders
from baykeshop.contrib.shop.services.pay_service import PayService
from baykeshop.db.security import security_logger

logger = logging.getLogger("baykeshop.contrib.shop")


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
        from baykeshop.contrib.shop.views.carts import _checkout_steps
        context = super().get_context_data(**kwargs)
        context["title"] = _("订单支付")
        context['checkout_steps'] = _checkout_steps(2)
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
        """支付宝同步通知 — 验签即代表支付宝身份，无需 CSRF"""
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
        logger.warning(
            "Alipay sync callback: sign verification failed for order_sn=%s", order_sn
        )
        return HttpResponse("success")

    def post(self, request, *args, **kwargs):
        """支付宝异步通知"""
        data = request.POST.dict()
        order_sn = data.get("out_trade_no")
        success = self.has_verify_sign(data)
        if success:
            # 服务端交易状态查询（第二道防线）
            trade_status = PayService.verify_trade(order_sn)
            if trade_status is False:
                security_logger.critical(
                    "PAYMENT_CALLBACK_MISMATCH | order_sn=%s | "
                    "验签通过但服务端查询返回未支付 — 拒绝处理",
                    order_sn,
                )
                return HttpResponse("success")
            elif trade_status is None:
                logger.warning(
                    "verify_trade 不可用 (order_sn=%s)，仅凭验签处理回调",
                    order_sn,
                )

            PayService.handle_payment_success(order_sn, data)
            return HttpResponse("success")
