import logging

from baykeshop.contrib.member.models import UserNotification

logger = logging.getLogger("baykeshop.contrib.member")


class NotificationService:
    """统一通知服务 — 站内消息 + 邮件/SMS 分派点"""

    @staticmethod
    def create(user, title, content='', related_url='', send_email=False):
        """创建站内通知"""
        notif = UserNotification.objects.create(
            user=user,
            title=title,
            content=content,
            related_url=related_url,
        )
        logger.info(f"通知已创建: user={user.username}, title={title}")
        return notif

    @staticmethod
    def get_unread_count(user):
        """获取未读通知数"""
        return UserNotification.objects.filter(user=user, is_read=False).count()

    @staticmethod
    def get_user_notifications(user, page=1, per_page=20):
        """获取用户通知列表（分页）"""
        qs = UserNotification.objects.filter(user=user)
        total = qs.count()
        start = (page - 1) * per_page
        end = start + per_page
        notifications = list(qs[start:end])
        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            'notifications': notifications,
            'total': total,
            'page': page,
            'total_pages': total_pages,
        }

    @staticmethod
    def mark_read(notification_id, user):
        """标记单个通知为已读"""
        UserNotification.objects.filter(id=notification_id, user=user).update(is_read=True)

    @staticmethod
    def mark_all_read(user):
        """标记所有通知为已读"""
        UserNotification.objects.filter(user=user, is_read=False).update(is_read=True)

    @classmethod
    def notify_stock_arrival(cls, goods):
        """商品补货时通知所有关注用户"""
        from baykeshop.contrib.shop.models import BaykeShopGoodsFollow
        follows = BaykeShopGoodsFollow.objects.filter(
            goods=goods, notify_type='arrival', is_notified=False
        )
        for follow in follows:
            cls.create(
                user=follow.user,
                title='商品到货通知',
                content=f'您关注的「{goods.name}」已到货，快去看看吧！',
                related_url=f'/detail/{goods.id}/',
            )
            follow.is_notified = True
            follow.save(update_fields=['is_notified'])
        return follows.count()

    @classmethod
    def notify_price_drop(cls, goods, old_price, new_price):
        """商品降价时通知所有关注用户"""
        from baykeshop.contrib.shop.models import BaykeShopGoodsFollow
        follows = BaykeShopGoodsFollow.objects.filter(
            goods=goods, notify_type='price_drop'
        )
        for follow in follows:
            cls.create(
                user=follow.user,
                title='商品降价通知',
                content=f'您关注的「{goods.name}」已从 ¥{old_price} 降至 ¥{new_price}',
                related_url=f'/detail/{goods.id}/',
            )
        return follows.count()
