from django.core.cache import cache
from django.template import Library

from baykeshop.contrib.shop.services.public_service import PublicService
from baykeshop.contrib.system.models import BaykeDictModel, Visit

register = Library()


@register.simple_tag
def dict_value(key):
    """获取字典值（带 1 小时缓存，减少 DB 查询）"""
    cache_key = f"dict:value:{key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    value = BaykeDictModel.get_key_value(key)
    if value is not None:
        cache.set(cache_key, value, timeout=3600)
    return value

@register.simple_tag
def visit_count(content_object:Visit, key:str):
    """访问统计"""
    return Visit.objects.get_uv_pv_count(content_object).get(key)


@register.inclusion_tag("baykeshop/tags/banners.html")
def banners_template():
    """ 轮播图 """
    return {
        'banners': PublicService.get_index_banners()
    }
