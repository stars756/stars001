"""
Celery Beat 周期性任务

电商系统常用周期任务：
- 自动关闭超时未支付订单
- 清理过期的验证码缓存（Redis TTL 兜底）
- 每日销售统计快照
- 缓存预热（首页热点数据）

使用方式：
    celery -A baykeshop beat -l info    # 启动 Beat 调度器
    celery -A baykeshop worker -l info   # 启动 Worker 执行任务
"""

import logging
from datetime import timedelta

from celery import shared_task

# cache 不再通过此文件直接操作，统一由 Service 层管理
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger("baykeshop.periodic_tasks")


# ============================================================
# 订单相关定时任务
# ============================================================

@shared_task(
    bind=True,
    name='baykeshop.auto_close_expired_orders',
    max_retries=1,
)
def auto_close_expired_orders(self):
    """
    [每5分钟] 自动关闭超时未支付订单
    
    业务规则：下单后 30 分钟内未支付，自动取消
    支持在 BAYKE_SETTINGS 中配置 ORDER_EXPIRE_MINUTES 覆盖默认值
    """
    try:
        from baykeshop.conf import bayke_settings
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        from baykeshop.db.orders import BaseOrdersModel

        # 从配置读取过期时间，默认30分钟
        expire_minutes = getattr(bayke_settings, 'ORDER_EXPIRE_MINUTES', None)
        if expire_minutes is None:
            expire_minutes = 30

        # 查找所有待支付且已过期的订单
        # 注意：StatusChoices 定义在 BaseOrdersModel 上
        cutoff = timezone.now() - timedelta(minutes=expire_minutes)

        expired_orders = BaykeShopOrders.objects.filter(
            status=BaseOrdersModel.OrderStatus.UNPAID,
            created_time__lte=cutoff,
        )

        expired_count = expired_orders.count()
        if expired_count == 0:
            return {'status': 'ok', 'closed': 0}

        # 逐条 save 触发 pre_save 信号 → apply_status_transition 恢复库存
        from django.db import transaction
        with transaction.atomic():
            updated = 0
            for order in expired_orders:
                order.status = BaseOrdersModel.OrderStatus.EXPIRED
                order.save(update_fields=['status'])
                updated += 1

        logger.info(
            f"[自动关单] 已关闭 {updated} 个超时未支付订单 "
            f"(超时阈值: {expire_minutes}分钟)"
        )

        return {
            'status': 'ok',
            'closed': updated,
            'expire_minutes': expire_minutes,
        }

    except Exception as e:
        logger.exception(f"[自动关单] 任务执行失败: {str(e)}")
        raise self.retry(exc=e, countdown=300)


@shared_task(
    bind=True,
    name='baykeshop.daily_order_statistics',
    max_retries=1,
)
def daily_order_statistics(self):
    """
    [每天凌晨1点] 生成前一天的销售统计快照
    
    统计内容：订单总数、成交总额、客单价、取消率等
    结果写入 Redis，供后台仪表盘读取
    """
    try:
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        from baykeshop.db.orders import BaseOrdersModel

        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        day_start = timezone.make_aware(
            datetime.combine(yesterday, time.min),
            timezone.get_current_timezone()
        )
        day_end = timezone.make_aware(
            datetime.combine(yesterday, time.max),
            timezone.get_current_timezone()
        )

        # 当日订单统计
        orders = BaykeShopOrders.objects.filter(created_time__range=[day_start, day_end])

        total_count = orders.count()
        paid_count = orders.filter(status__in=[
            BaseOrdersModel.OrderStatus.PAID,
            BaseOrdersModel.OrderStatus.SHIPPED,
            BaseOrdersModel.OrderStatus.DONE,
        ]).count()

        total_amount = orders.filter(
            status__in=[
                BaseOrdersModel.OrderStatus.PAID,
                BaseOrdersModel.OrderStatus.SHIPPED,
                BaseOrdersModel.OrderStatus.DONE,
            ]
        ).aggregate(total=Sum('pay_price'))['total'] or 0  # pay_price 是实际数据库字段

        canceled_count = orders.filter(
            status=BaseOrdersModel.OrderStatus.EXPIRED
        ).count()

        stats = {
            'date': str(yesterday),
            'total_orders': total_count,
            'paid_orders': paid_count,
            'canceled_orders': canceled_count,
            'total_amount': float(total_amount),
            'avg_order_value': round(float(total_amount / paid_count), 2) if paid_count > 0 else 0,
            'cancel_rate': round(canceled_count / total_count * 100, 2) if total_count > 0 else 0,
        }

        logger.info(
            f"[日统计] {yesterday} — 总订单: {total_count}, "
            f"已支付: {paid_count}, 成交额: ¥{total_amount}, 取消率: {stats['cancel_rate']}%"
        )

        return stats

    except Exception as e:
        logger.exception(f"[日统计] 任务执行失败: {str(e)}")
        raise self.retry(exc=e, countdown=3600)


# ============================================================
# 缓存维护任务
# ============================================================

@shared_task(
    bind=True,
    name='baykeshop.cache_warmup_homepage',
    max_retries=1,
)
def cache_warmup_homepage(self):
    """
    [每10分钟] 首页热点数据缓存预热

    预热数据：
    - 轮播图列表 (banners:index)
    - 首页楼层商品 (floors:index)

    注意：预热 key 必须与页面实际读取的 key 一致。
    页面读取路径：
    - 轮播图：baykeconfig.py → PublicService.get_index_banners() → "banners:index"
    - 导航分类：header.html → {% navs %} → "tt:navs:{is_nav}"（模板标签自带 5 分钟缓存，无需预热）
    """
    try:
        warmed_keys = []
        from baykeshop.contrib.shop.services.public_service import PublicService

        # 轮播图和楼层 — Service 方法内部已写缓存，直接调用即可
        PublicService.get_index_banners()
        warmed_keys.append(PublicService._BANNERS_CACHE_KEY)

        PublicService.get_index_floors()
        warmed_keys.append(PublicService._FLOORS_CACHE_KEY)

        logger.info(f"[缓存预热] 首页数据预热完成, 共 {len(warmed_keys)} 个key: {warmed_keys}")

        return {
            'status': 'ok',
            'warmed_keys': warmed_keys,
            'count': len(warmed_keys),
        }

    except Exception as e:
        logger.exception(f"[缓存预热] 任务执行失败: {str(e)}")
        raise self.retry(exc=e, countdown=60)


# ============================================================
# 安全清理任务
# ============================================================

@shared_task(
    bind=True,
    name='baykeshop.cleanup_expired_tokens',
    max_retries=1,
)
def cleanup_expired_tokens(self):
    """
    [每小时] 清理过期的邮箱验证 Token
    
    将超过有效期但尚未验证的用户记录标记为需要重新验证
    （正常情况下用户会自己验证或重新发送，
     此任务作为兜底清理长时间未处理的脏数据）
    
    注意：此任务不会删除用户，只清除无效 token
    """
    try:
        from baykeshop.conf import bayke_settings
        from baykeshop.contrib.member.models import BaykeShopUser

        expire_seconds = bayke_settings.EMAIL_VERIFY_TOKEN_EXPIRE_SECONDS  # 默认86400秒(24h)
        cutoff = timezone.now() - timedelta(seconds=expire_seconds)

        # 找到 token 过期但 still 未验证 且 verification_token_created_at 早于截止时间的用户
        stale_users = BaykeShopUser.objects.filter(
            is_email_verified=False,
            email_verification_token__isnull=False,
            verification_token_created_at__lt=cutoff,
        )

        cleared_count = stale_users.count()
        if cleared_count > 0:
            # 只清除 token，不影响用户登录状态
            stale_users.update(email_verification_token=None, verification_token_created_at=None)

            logger.info(f"[Token清理] 已清除 {cleared_count} 个过期验证Token")
        else:
            logger.debug("[Token清理] 无需清理")

        return {'status': 'ok', 'cleared': cleared_count}

    except Exception as e:
        logger.exception(f"[Token清理] 任务执行失败: {str(e)}")
        raise self.retry(exc=e, countdown=1800)


# ============================================================
# 补充导入
# ============================================================
from datetime import datetime, time
