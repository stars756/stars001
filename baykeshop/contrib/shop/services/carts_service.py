import json
import logging

from baykeshop.contrib.shop.models import BaykeShopCarts

logger = logging.getLogger("baykeshop.contrib.shop")


class CartsService:
    """购物车服务"""

    @staticmethod
    def get_user_carts_list(user):
        """
        获取用户购物车列表

        Args:
            user: 用户对象

        Returns:
            list: 购物车项列表，包含格式化后的规格数据
        """
        queryset = BaykeShopCarts.objects.filter(user=user).order_by('-created_time')
        queryset = list(queryset.values(
            'id', 'total_price', 'name', 'specs', 'image_url', 'sku_id',
            'sku__price', 'sku__stock', 'sku__sales', 'quantity'
        ))
        for item in queryset:
            specs = item['specs']
            if isinstance(specs, str):
                item['specs'] = json.loads(specs)
            item['total_price'] = round(item['total_price'], 2)
        return queryset
