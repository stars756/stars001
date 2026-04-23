from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from baykeshop.contrib.shop.models import BaykeShopOrdersGoods, BaykeShopOrders


@receiver(post_save, sender=BaykeShopOrdersGoods)
def sku_stock_update(sender, instance, created, **kwargs):
    """
    订单关联商品保存成功 减库存（锁定库存）

    注意：只在新增记录时触发（created=True），避免更新操作重复扣减库存
    确保库存操作的幂等性和数据一致性
    """
    if not created:
        return

    from django.db.models import F
    sku = instance.sku
    if sku:  # 防止sku被删除
        # 只减库存，不加销量
        sku.stock = F("stock") - instance.quantity
        sku.save()


@receiver(pre_save, sender=BaykeShopOrders)
def handle_order_status_change(sender, instance, **kwargs):
    """
    处理订单状态变更
    1. 支付超时/取消订单：回滚库存
    2. 支付完成：增加销量
    3. 已支付订单退款：回滚库存并减少销量
    """
    if instance.pk is None:
        return  # 新订单创建时不处理

    try:
        old_order = BaykeShopOrders.objects.get(pk=instance.pk)
        old_status = old_order.status
        new_status = instance.status

        # 状态未改变，不处理
        if old_status == new_status:
            return

        from django.db.models import F

        # 获取订单关联的商品
        order_goods = instance.baykeshopordersgoods_set.all()

        for order_good in order_goods:
            sku = order_good.sku
            if not sku:
                continue

            quantity = order_good.quantity

            # 情况1：未支付订单取消（状态变为EXPIRED）- 只回滚库存
            if old_status == BaykeShopOrders.OrderStatus.UNPAID and new_status == BaykeShopOrders.OrderStatus.EXPIRED:
                # 回滚库存（增加库存），销量不变
                sku.stock = F("stock") + quantity
                sku.save()

            # 情况2：支付完成（从UNPAID变为PAID或SHIPPED或VERIFY）- 增加销量
            elif old_status == BaykeShopOrders.OrderStatus.UNPAID and new_status in [
                BaykeShopOrders.OrderStatus.PAID,
                BaykeShopOrders.OrderStatus.SHIPPED,
                BaykeShopOrders.OrderStatus.VERIFY
            ]:
                # 增加销量，库存已在创建订单时扣减
                sku.sales = F("sales") + quantity
                sku.save()

            # 情况3：已支付订单被取消/退款 - 回滚库存并减少销量
            elif old_status not in [
                BaykeShopOrders.OrderStatus.UNPAID,
                BaykeShopOrders.OrderStatus.EXPIRED
            ] and new_status in [
                BaykeShopOrders.OrderStatus.EXPIRED,
                BaykeShopOrders.OrderStatus.REFUNDED
            ]:
                # 回滚库存（增加库存）
                sku.stock = F("stock") + quantity
                # 减少销量（因为之前已经增加过销量）
                sku.sales = F("sales") - quantity
                sku.save()

            # 情况4：从未支付直接退款（异常情况）- 只回滚库存
            elif old_status == BaykeShopOrders.OrderStatus.UNPAID and new_status == BaykeShopOrders.OrderStatus.REFUNDED:
                # 回滚库存（增加库存），销量不变
                sku.stock = F("stock") + quantity
                sku.save()

    except BaykeShopOrders.DoesNotExist:
        pass  # 订单不存在，不处理