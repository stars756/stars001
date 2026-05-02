from django.db.models.signals import pre_save
from django.dispatch import receiver

from baykeshop.contrib.shop.models import BaykeShopOrders
from baykeshop.contrib.shop.services.order_service import OrderService


@receiver(pre_save, sender=BaykeShopOrders)
def handle_order_status_change(sender, instance, **kwargs):
    """
    处理订单状态变更 — 委托 OrderService.apply_status_transition

    信号只负责检测状态变更并获取旧状态，
    所有库存/销量的增删逻辑统一由 OrderService 维护。
    """
    if instance.pk is None:
        return

    try:
        old_order = BaykeShopOrders.objects.only('status').get(pk=instance.pk)
    except BaykeShopOrders.DoesNotExist:
        return

    if old_order.status == instance.status:
        return

    OrderService.apply_status_transition(instance, old_order.status)
