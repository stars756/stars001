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
from django.utils import timezone
from django.core.cache import cache as django_cache
from django.db.models import Sum, Count

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
        from baykeshop.contrib.shop.models.orders import BaykeShopOrders
        from baykeshop.conf import bayke_settings
        
        # 从配置读取过期时间，默认30分钟
        expire_minutes = getattr(bayke_settings, 'ORDER_EXPIRE_MINUTES', None)
        if expire_minutes is None:
            expire_minutes = 30
            
        # 查找所有待支付且已过期的订单
        cutoff = timezone.now() - timedelta(minutes=expire_minutes)
        
        expired_orders = BaykeShopOrders.objects.filter(
            status=BaykeShopOrders.StatusChoices.UNPAID,
            created_time__lte=cutoff,
        )
        
        expired_count = expired_orders.count()
        if expired_count == 0:
            return {'status': 'ok', 'closed': 0}
            
        # 批量关闭
        updated = expired_orders.update(status=BaykeShopOrders.StatusChoices.CANCELED)
        
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
            BaykeShopOrders.StatusChoices.PAID,
            BaykeShopOrders.StatusChoices.SHIPPED,
            BaykeShopOrders.StatusChoices.COMPLETED,
        ]).count()
        
        total_amount = orders.filter(
            status__in=[
                BaykeShopOrders.StatusChoices.PAID,
                BaykeShopOrders.StatusChoices.SHIPPED,
                BaykeShopOrders.StatusChoices.COMPLETED,
            ]
        ).aggregate(total=Sum('total_price'))['total'] or 0
        
        canceled_count = orders.filter(
            status=BaykeShopOrders.StatusChoices.CANCELED
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
        
        # 写入 Redis（保留90天）
        django_cache.set(f"stats:daily:{yesterday}", stats, timeout=90 * 86400)
        
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
    - 轮播图列表
    - 首页楼层商品
    - 热门/推荐商品
    
    目的：避免用户访问首页时触发冷查询
    """
    try:
        warmed_keys = []
        
        # 1. 预热轮播图
        from baykeshop.contrib.system.models import BaykeBannerModel
        banners = list(BaykeBannerModel.objects.filter(is_active=True).values())
        django_cache.set('banners:active', banners, timeout=600)
        warmed_keys.append('banners:active')
        
        # 2. 预热推荐商品（按创建时间倒序取前20）
        from baykeshop.contrib.shop.models.goods import BaykeShopGoodsSPU
        recommended = list(
            BaykeShopGoodsSPU.objects.filter(
                is_show=True, is_delete=False,
            ).select_related('category').order_by('-created_time')[:20]
        )
        django_cache.set('goods:recommended_top20', recommended, timeout=300)
        warmed_keys.append('goods:recommended_top20')
        
        # 3. 预热分类导航（带商品计数）
        from baykeshop.contrib.shop.models.goods import BaykeShopCategory
        categories_with_counts = list(
            BaykeShopCategory.objects.annotate(
                goods_count=Count('goodsspu_set')
            ).filter(goods_count__gt=0)[:15]
        )
        django_cache.set('nav:categories_with_counts', categories_with_counts, timeout=300)
        warmed_keys.append('nav:categories_with_counts')
        
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
        from baykeshop.contrib.member.models import BaykeShopUser
        from baykeshop.conf import bayke_settings
        
        expire_seconds = bayke_settings.EMAIL_VERIFY_TOKEN_EXPIRE_SECONDS  # 默认86400秒(24h)
        cutoff = timezone.now() - timedelta(seconds=expire_seconds)
        
        # 找到 token 过期但 still 未验证 且 email_verify_at 早于截止时间的用户
        stale_users = BaykeShopUser.objects.filter(
            is_email_verified=False,
            email_verification_token__isnull=False,
            email_verify_at__lt=cutoff,
        )
        
        cleared_count = stale_users.count()
        if cleared_count > 0:
            # 只清除 token，不影响用户登录状态
            stale_users.update(email_verification_token=None, email_verify_at=None)
            
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
