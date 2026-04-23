from django.db import models
from django.utils.translation import gettext_lazy as _

from baykeshop.db import BaseOrdersModel, BaseOrdersGoodsModel
from .goods import BaykeShopGoodsSKU


class BaykeShopOrders(BaseOrdersModel):
    """订单表"""

    class Meta(BaseOrdersModel.Meta):
        verbose_name = _('订单')
        verbose_name_plural = verbose_name
        ordering = ['-created_time']
        
    def __str__(self):
        return self.order_sn
    
    @property
    def total_price(self):
        return self.pay_price
    
    @property
    def total_quantity(self):
        return self.baykeshopordersgoods_set.count()
    
    # 判断是否为虚拟商品订单,并且订单状态为待收货
    @property
    def is_virtual(self):
        order_goods = self.baykeshopordersgoods_set.first()
        return order_goods.sku.goods.is_virtual and (1 < self.status < 5)
    
    @property
    def virtual_content(self):
        order_goods = self.baykeshopordersgoods_set.first()
        return order_goods.sku.email_message
    

class BaykeShopOrdersGoods(BaseOrdersGoodsModel):
    """订单商品表"""
    sku = models.ForeignKey(BaykeShopGoodsSKU, on_delete=models.SET_NULL, verbose_name=_('商品'), null=True)
    orders = models.ForeignKey(BaykeShopOrders, on_delete=models.CASCADE, verbose_name=_('订单'))

    class Meta:
        verbose_name = _('订单商品')
        verbose_name_plural = verbose_name
        ordering = ['-created_time']
        constraints = [
            models.UniqueConstraint(fields=['sku', 'orders'], name='sku_orders_unique')
        ]

    def __str__(self):
        return self.name