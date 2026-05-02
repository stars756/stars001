import logging
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator

from baykeshop.contrib.system.models import Visit
from baykeshop.contrib.article.models import (
    BaykeArticleCategory, BaykeArticleTags, BaykeArticleContent
)
from baykeshop.contrib.article.models import BaykeSidebar

logger = logging.getLogger("baykeshop.contrib.article")


class ArticleService:
    """文章服务"""

    def search_articles(self, queryset, keyword):
        """搜索文章"""
        if keyword:
            keyword = keyword.strip()
            if len(keyword) > 100:
                raise ValueError(_('搜索内容过长'))
            queryset = queryset.filter(title__icontains=keyword)
        return queryset

    def get_category_articles(self, category):
        """获取分类下的文章"""
        return category.baykearticlecontent_set.all()

    def get_tag_articles(self, tag):
        """获取标签下的文章"""
        return tag.baykearticlecontent_set.all()

    def get_user_articles(self, user):
        """获取用户的文章"""
        return user.baykearticlecontent_set.all()

    def create_article_pv_uv(self, request, article):
        """创建文章PV/UV记录"""
        Visit.objects.create_pv_uv(request, article)
        return article

    def get_article_by_pk(self, pk, queryset=None):
        """根据主键获取文章"""
        if queryset is None:
            queryset = BaykeArticleContent.objects.all()
        return queryset.get(pk=pk)

    def get_article_list_queryset(self):
        """获取文章列表的基础查询集（预取标签避免模板 N+1）"""
        return BaykeArticleContent.objects.prefetch_related('tags').order_by('-created_time')

    def get_archive_months(self):
        """获取文章归档月份列表"""
        return BaykeArticleContent.objects.dates(field_name="created_time", kind="month")

    def get_paginated_articles(self, queryset, page_number=1, per_page=10):
        """获取分页后的文章列表"""
        paginator = Paginator(queryset, per_page)
        return paginator.get_page(page_number)

    def get_sidebar_data(self):
        """获取侧边栏数据"""
        sidebar_items = BaykeSidebar.objects.filter(is_show=True).order_by('order')
        categories = BaykeArticleCategory.objects.filter(
            parent__isnull=True
        ).prefetch_related('baykearticlecategory_set')
        tags = self.get_sidebar_tags()
        archive_months = BaykeArticleContent.objects.dates(
            field_name="created_time", kind="month"
        )[:12]

        return {
            'sidebar_items': sidebar_items,
            'categories': categories,
            'tags': tags,
            'archive_months': archive_months,
        }

    def get_sidebar_tags(self):
        """获取侧边栏标签（含文章计数）"""
        from django.db.models import Count
        return BaykeArticleTags.objects.annotate(
            count=Count('baykearticlecontent')
        ).order_by('-count')[:20]

    def get_prev_article(self, article):
        """获取上一篇文章"""
        return BaykeArticleContent.objects.filter(
            created_time__lt=article.created_time
        ).order_by('-created_time').first()

    def get_next_article(self, article):
        """获取下一篇文章"""
        return BaykeArticleContent.objects.filter(
            created_time__gt=article.created_time
        ).order_by('created_time').first()


article_service = ArticleService()
