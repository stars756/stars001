from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '清除首页楼层、轮播图、商品详情等热点缓存'

    def handle(self, *args, **options):
        keys = [
            'floors:index',
            'banners:index',
            'tt:navs:0',
            'tt:navs:1',
        ]
        cache.delete_many(keys)
        self.stdout.write(self.style.SUCCESS(f'已清除 {len(keys)} 个热点缓存键'))
