import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
from alipay.aop.api.util.SignatureUtils import sign_with_rsa2, verify_with_rsa
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from baykeshop.contrib.shop.models.orders import BaykeShopOrders
from baykeshop.contrib.shop.services.order_service import OrderService
from baykeshop.contrib.system.models import BaykeDictModel
from baykeshop.db.orders import BaseOrdersModel  # OrderStatus 定义在基类上
from baykeshop.db.security import security_logger

logger = logging.getLogger("baykeshop.contrib.shop")


class PayService:
    """支付服务"""

    @staticmethod
    def has_verify_sign(data):
        """
        支付宝支付回调验签

        Args:
            data: 从请求中获得的字典数据，携带 sign和sign_type

        Returns:
            bool: 验签是否通过
        """
        sign = data.pop("sign")
        sign_type = data.pop("sign_type")
        alipay_public_key = BaykeDictModel.get_key_value("ALIPAY_PUBLIC_KEY")
        if not alipay_public_key:
            logger.error("has_verify_sign: ALIPAY_PUBLIC_KEY 未配置，验签中止")
            return False
        # 去除sign和sign_type参数之后进行升序排列，拼装请求参数用支付宝公钥进行验签
        message = "&".join(
            [
                f"{k}={v}"
                for k, v in dict(
                    sorted(data.items(), key=lambda d: d[0], reverse=False)
                ).items()
            ]
        )
        flag = verify_with_rsa(
            alipay_public_key, message.encode("UTF-8", "strict"), sign
        )
        return flag

    @staticmethod
    def verify_trade(order_sn):
        """
        服务端交易状态查询（第二道防线）。

        使用 requests 调支付宝 alipay.trade.query 接口，
        双重确认交易状态。永不抛异常，所有外部调用均已 try/except 兜底。

        Args:
            order_sn: 商户订单号 (out_trade_no)

        Returns:
            True  — 交易状态为 TRADE_SUCCESS 或 TRADE_FINISHED
            False — 交易状态为其他（未支付、已关闭等）
            None  — 查询失败（网络超时、配置缺失等）
        """
        app_id = BaykeDictModel.get_key_value("ALIPAY_APPID")
        app_private_key = BaykeDictModel.get_key_value("ALIPAY_PRIVATE_KEY")
        alipay_public_key = BaykeDictModel.get_key_value("ALIPAY_PUBLIC_KEY")

        if not all([app_id, app_private_key, alipay_public_key]):
            logger.error("verify_trade: Alipay 配置缺失（APPID/密钥）")
            return None

        gateway = (
            "https://openapi.alipay.com/gateway.do"
            if not settings.DEBUG
            else "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
        )

        biz_content = json.dumps(
            {"out_trade_no": order_sn}, separators=(",", ":")
        )
        params = {
            "app_id": app_id,
            "method": "alipay.trade.query",
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": biz_content,
        }

        # 构建签名内容（按 key 排序）
        sign_content = "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        try:
            sign = sign_with_rsa2(app_private_key, sign_content, "utf-8")
        except Exception as e:
            logger.exception("verify_trade: 签名失败: %s", e)
            return None

        params["sign"] = sign

        # 发起 HTTP 查询
        try:
            resp = requests.post(
                gateway,
                data=params,
                timeout=10,
                headers={
                    "Content-Type":
                    "application/x-www-form-urlencoded;charset=utf-8"
                },
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(
                "verify_trade: 查询失败 (order_sn=%s): %s", order_sn, e
            )
            return None

        # 解析响应
        try:
            resp_data = resp.json()
            query_resp = resp_data.get("alipay_trade_query_response")
            resp_sign = resp_data.get("sign")
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(
                "verify_trade: 响应解析失败 (order_sn=%s): %s", order_sn, e
            )
            return None

        if not query_resp or not resp_sign:
            logger.warning(
                "verify_trade: 响应缺少必要字段 (order_sn=%s)", order_sn
            )
            return None

        # 验证响应签名 — 从原始文本中移除 sign 字段，保留原始字段顺序
        try:
            cleaned = re.sub(r',"sign":"[^"]*"', '', resp.text)
            cleaned = re.sub(r'"sign":"[^"]*",?', '', cleaned)
            if not verify_with_rsa(
                alipay_public_key,
                cleaned.encode("utf-8"),
                resp_sign,
            ):
                security_logger.critical(
                    "TRADE_QUERY_SIGN_MISMATCH | order_sn=%s | "
                    "响应签名验证失败",
                    order_sn,
                )
        except Exception as e:
            logger.warning(
                "verify_trade: 响应签名验证异常 (order_sn=%s): %s",
                order_sn, e,
            )

        # 判断交易状态
        code = query_resp.get("code")
        trade_status = query_resp.get("trade_status")

        if code == "10000" and trade_status in (
            "TRADE_SUCCESS", "TRADE_FINISHED"
        ):
            logger.info(
                "verify_trade: 交易确认 | order_sn=%s | trade_no=%s | "
                "status=%s",
                order_sn, query_resp.get("trade_no"), trade_status,
            )
            return True

        security_logger.warning(
            "TRADE_QUERY_UNCONFIRMED | order_sn=%s | code=%s | "
            "trade_status=%s",
            order_sn, code, trade_status,
        )
        return False

    @staticmethod
    def is_virtual_order(order):
        """判断订单是否为虚拟商品订单，委托给 OrderService（唯一规范来源）"""
        return OrderService.is_virtual_goods(order)

    @staticmethod
    def handle_payment_success(order_sn, data):
        """
        处理支付成功逻辑（幂等安全 — 可重复调用）

        Args:
            order_sn: 订单号
            data: 支付宝回调数据字典

        Returns:
            tuple: (bool, str) 是否成功处理，错误消息（如果有）
        """
        try:
            with transaction.atomic():
                order = BaykeShopOrders.objects.select_for_update().filter(
                    order_sn=order_sn
                ).first()
                if not order:
                    return False, "订单不存在"

                # 幂等守卫：已进入支付后状态的订单无需重复处理
                if order.status not in (
                    BaseOrdersModel.OrderStatus.UNPAID,
                    BaseOrdersModel.OrderStatus.EXPIRED,
                ):
                    return True, "已支付，无需重复处理"

                # 金额校验：防御签名绕过或金额篡改
                try:
                    paid_amount = Decimal(data.get("total_amount", "0"))
                except InvalidOperation:
                    security_logger.critical(
                        "PAYMENT_AMOUNT_PARSE_ERROR | order_sn=%s | raw=%s",
                        order_sn, data.get("total_amount")
                    )
                    return False, "支付金额格式异常"
                if paid_amount != order.pay_price:
                    security_logger.critical(
                        "PAYMENT_AMOUNT_MISMATCH | order_sn=%s | expected=%s | got=%s",
                        order_sn, order.pay_price, paid_amount
                    )
                    return False, "支付金额与订单不匹配"

                order.pay_time = timezone.now()
                order.pay_sn = data.get("trade_no")
                order.status = (
                    BaseOrdersModel.OrderStatus.VERIFY  # 虚拟商品 → 待核销
                    if PayService.is_virtual_order(order)
                    else BaseOrdersModel.OrderStatus.PAID  # 实物商品 → 待发货（PAID）
                )
                order.save()

            # 支付成功安全审计日志
            security_logger.info(
                "PAYMENT_SUCCESS | user=%s | order_sn=%s | trade_no=%s | amount=%s | status=%s",
                order.user.username, order_sn,
                data.get("trade_no"),
                data.get("total_amount", "unknown"),
                order.get_status_display()
            )

            return True, "支付成功"
        except Exception as e:
            logger.exception(f"处理支付成功逻辑失败: {str(e)}")
            return False, f"处理支付成功逻辑失败: {str(e)}"

    @staticmethod
    def get_user_orders_queryset(user):
        """
        获取用户的订单查询集（含关联数据预取，避免模板遍历 N+1）

        Args:
            user: 用户对象

        Returns:
            QuerySet: 用户的订单查询集
        """
        return BaykeShopOrders.objects.select_related('user').prefetch_related(
            'baykeshopordersgoods_set',
            'baykeshopordersgoods_set__sku',
            'baykeshopordersgoods_set__sku__goods',
        ).filter(user=user)
