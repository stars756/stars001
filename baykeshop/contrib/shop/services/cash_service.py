import logging

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from baykeshop.contrib.shop.models import BaykeShopCarts, BaykeShopGoodsSKU

logger = logging.getLogger("baykeshop.contrib.shop")


class CashService:
    """收银台服务"""

    @staticmethod
    def has_carts_from_kwargs(kwargs):
        """
        判断是否来自购物车

        Args:
            kwargs: 视图的kwargs参数字典

        Returns:
            bool: 是否来自购物车
        """
        return 'skuids' in kwargs

    @staticmethod
    def _validate_and_parse_sku_ids(skuids_str):
        """
        验证并解析SKU ID字符串

        输入格式："1,2,3" 或单个 "1"
        输出：整数列表

        Raises:
            ValidationError: 当格式无效或包含非数字字符时
        """
        if not skuids_str or not skuids_str.strip():
            raise ValidationError("SKU ID不能为空")

        try:
            skuids = [int(skuid.strip()) for skuid in skuids_str.split(',')]
            # 验证所有ID均为正整数
            for skuid in skuids:
                if skuid <= 0:
                    raise ValidationError(f"SKU ID必须为正整数: {skuid}")
            return skuids
        except ValueError as e:
            raise ValidationError(f"SKU ID格式错误: {skuids_str}") from e

    @staticmethod
    def get_cash_queryset(kwargs, user=None):
        """
        获取收银台商品数据

        Args:
            kwargs: 视图的kwargs参数字典
            user: 用户对象（可选，用于购物车查询）

        Returns:
            QuerySet: 商品查询集，包含total_price和quantity注解

        Raises:
            ValidationError: 当SKU ID格式无效时
        """
        skuids = []
        if CashService.has_carts_from_kwargs(kwargs):
            # 使用验证方法，避免直接转换可能引发的ValueError
            skuids_str = kwargs.get('skuids', '')
            skuids = CashService._validate_and_parse_sku_ids(skuids_str)
            queryset = BaykeShopCarts.objects.filter(sku_id__in=skuids, user=user)
            return queryset
        else:
            # 单个商品场景
            skuid_str = str(kwargs.get('skuid', ''))
            num = kwargs.get('num', 1)
            try:
                skuids = [int(skuid_str)] if skuid_str else []
            except ValueError:
                raise ValidationError(f"SKU ID格式错误: {skuid_str}")

            if not skuids:
                raise ValidationError("SKU ID不能为空")

            queryset = BaykeShopGoodsSKU.objects.filter(id__in=skuids).annotate(
                total_price=models.ExpressionWrapper(
                    models.F('price') * models.Value(num, output_field=models.IntegerField()),
                    output_field=models.DecimalField()
                ),
                quantity=models.Value(num, output_field=models.IntegerField()),
            )
            return queryset

    @staticmethod
    def get_total_price(queryset):
        """
        计算总价（使用 DB aggregate 而非 Python sum，避免全量加载到内存）
        """
        result = queryset.aggregate(total=Sum('total_price'))
        return result['total'] or 0

    @staticmethod
    def get_total_count(queryset):
        """
        计算总数量（使用 DB aggregate 而非 Python sum）
        """
        result = queryset.aggregate(total=Sum('quantity'))
        return result['total'] or 0
