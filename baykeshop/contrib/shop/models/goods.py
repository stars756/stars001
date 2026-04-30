from django.db import models
from django.utils.translation import gettext_lazy as _

from baykeshop.db.fields import RichTextField
from baykeshop.db import (
    BaseModel,
    BaseGoodsModel,
    BaseGoodsSKUModel,
    BaseCategoryModel,
    BaseCartsModel,
)
from .managers import (
    BaykeShopGoodsManager,
    BaykeShopCartsManager,
    BaykeShopGoodsSKUManager,
)


class BaykeShopCategory(BaseCategoryModel):
    """商品分类"""

    icon = models.CharField(
        max_length=50, blank=True, default="", verbose_name=_("图标")
    )
    is_floor = models.BooleanField(default=False, verbose_name=_("是否楼层"))
    is_nav = models.BooleanField(default=False, verbose_name=_("是否导航"))

    class Meta:
        verbose_name = _("商品分类")
        verbose_name_plural = _("商品分类")
        ordering = ["order"]

    def __str__(self):
        return self.name


class BaykeShopBrand(BaseModel):
    """商品品牌"""

    name = models.CharField(max_length=50, verbose_name=_("品牌名称"))
    image = models.ImageField(
        upload_to="brand", blank=True, null=True, verbose_name=_("品牌图片")
    )
    order = models.IntegerField(default=0, verbose_name=_("排序"))
    description = models.TextField(blank=True, null=True, verbose_name=_("品牌介绍"))

    class Meta:
        verbose_name = _("商品品牌")
        verbose_name_plural = verbose_name
        ordering = ["order"]

    def __str__(self):
        return self.name


class BaykeShopGoods(BaseGoodsModel):
    """商品"""

    category = models.ManyToManyField(
        BaykeShopCategory, blank=True, verbose_name=_("商品分类")
    )
    brand = models.ForeignKey(
        BaykeShopBrand,
        on_delete=models.SET_NULL,
        verbose_name=_("商品品牌"),
        blank=True,
        null=True,
    )
    # 推荐
    is_recommend = models.BooleanField(default=False, verbose_name=_("商品推荐"))
    # 是否为虚拟商品
    is_virtual = models.BooleanField(
        default=False, 
        verbose_name=_("是否为虚拟商品"), 
        help_text=_("虚拟商品不需要物流")
    )

    objects = BaykeShopGoodsManager()

    class Meta:
        verbose_name = _("商品")
        verbose_name_plural = _("商品")
        ordering = ["-created_time"]

    def __str__(self):
        return self.name

    def has_many_sku(self):
        return self.baykeshopgoodssku_set.count() > 1


class BaykeShopGoodsSKU(BaseGoodsSKUModel):
    """商品SKU"""

    goods = models.ForeignKey(
        BaykeShopGoods, on_delete=models.CASCADE, verbose_name=_("商品")
    )
    email_message = RichTextField(
        blank=True,
        default='',
        verbose_name=_("虚拟商品邮件内容"),
        help_text=_("如果SPU整体为虚拟商品，则填写虚拟商品邮件内容，付款成功后，会发送邮件给用户"),
    )

    objects = BaykeShopGoodsSKUManager()

    class Meta:
        verbose_name = _("商品SKU")
        verbose_name_plural = _("商品SKU")
        ordering = ["-created_time"]

    def __str__(self):
        return self.goods.name

    def save(self, *args, **kwargs):
        """覆盖 save — 库存从0恢复时触发到货通知"""
        is_new = self.pk is None
        old_stock = None
        if not is_new:
            old_stock = BaykeShopGoodsSKU.objects.filter(
                pk=self.pk
            ).values_list('stock', flat=True).first()

        super().save(*args, **kwargs)

        if old_stock is not None:
            if old_stock == 0:
                self.refresh_from_db()
                if self.stock > 0:
                    from baykeshop.contrib.member.services.notification_service import (
                        NotificationService
                    )
                    NotificationService.notify_stock_arrival(self.goods)
            elif old_stock > 0:
                self.refresh_from_db()
                if self.stock == 0:
                    BaykeShopGoodsFollow.objects.filter(
                        goods=self.goods, notify_type='arrival'
                    ).update(is_notified=False)


class BaykeShopCarts(BaseCartsModel):
    """购物车"""

    sku = models.ForeignKey(
        BaykeShopGoodsSKU, on_delete=models.CASCADE, verbose_name=_("商品")
    )

    objects = BaykeShopCartsManager()

    class Meta:
        verbose_name = _("购物车")
        verbose_name_plural = _("购物车")
        ordering = ["-created_time"]
        constraints = [
            models.UniqueConstraint(fields=["user", "sku"], name="unique_carts")
        ]

    def __str__(self):
        return f"{self.user.username} - {self.sku.goods.name}"


class BaykeShopSpec(BaseCategoryModel):
    """商品规格"""

    class Meta:
        verbose_name = _("规格模版")
        verbose_name_plural = _("规格模版")
        ordering = ["-created_time"]

    def __str__(self):
        if not self.parent:
            return self.name
        return f"{self.parent.name}:{self.name}"


class BaykeShopGoodsFavorite(BaseModel):
    """商品收藏"""

    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, verbose_name=_("用户")
    )
    goods = models.ForeignKey(
        BaykeShopGoods, on_delete=models.CASCADE, verbose_name=_("商品")
    )

    class Meta:
        verbose_name = _("商品收藏")
        verbose_name_plural = verbose_name
        ordering = ["-created_time"]
        constraints = [
            models.UniqueConstraint(fields=["user", "goods"], name="unique_favorite")
        ]

    def __str__(self):
        return f"{self.user.username} - {self.goods.name}"


class BaykeShopGoodsFollow(BaseModel):
    """商品关注（到货通知/降价通知）"""

    class NotifyType(models.TextChoices):
        ARRIVAL = 'arrival', _('到货通知')
        PRICE_DROP = 'price_drop', _('降价通知')

    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, verbose_name=_("用户")
    )
    goods = models.ForeignKey(
        BaykeShopGoods, on_delete=models.CASCADE, verbose_name=_("商品")
    )
    notify_type = models.CharField(
        max_length=20,
        choices=NotifyType.choices,
        default=NotifyType.ARRIVAL,
        verbose_name=_("通知类型")
    )
    is_notified = models.BooleanField(default=False, verbose_name=_("是否已通知"))

    class Meta:
        verbose_name = _("商品关注")
        verbose_name_plural = verbose_name
        ordering = ["-created_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "goods", "notify_type"], name="unique_follow"
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.goods.name} ({self.get_notify_type_display()})"


class BaykeShopGoodsImages(BaseModel):
    """商品图片"""

    goods = models.ForeignKey(
        BaykeShopGoods, on_delete=models.CASCADE, verbose_name=_("商品")
    )
    image = models.ImageField(
        upload_to="goods/images",
        verbose_name=_("商品图片"),
        help_text=_("建议尺寸: 800*800，排在第一个的图片会作为商品主图"),
    )
    order = models.IntegerField(default=0, verbose_name=_("排序"))

    class Meta:
        verbose_name = _("商品图片")
        verbose_name_plural = _("商品图片")
        ordering = ["order"]

    def __str__(self):
        return self.goods.name
    