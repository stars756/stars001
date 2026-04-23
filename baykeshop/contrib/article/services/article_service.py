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

    @staticmethod           
    def search_articles(queryset, keyword):
        """
        搜索文章

        Args:
            queryset: 基础查询集
            keyword: 搜索关键词

        Returns:
            QuerySet: 搜索后的查询集

        Raises:
            ValueError: 当搜索内容过长时
        """
        if keyword:
            keyword = keyword.strip()       # 去空格，减少搜索时间
            if len(keyword) > 100:
                raise ValueError(_('搜索内容过长'))
            queryset = queryset.filter(title__icontains=keyword)        # 使用icontains进行不区分大小写的模糊搜索，提升用户体验。
        return queryset

    @staticmethod
    def get_category_articles(category):
        """
        获取分类下的文章

        Args:
            category: BaykeArticleCategory 实例

        Returns:
            QuerySet: 文章查询集
        """
        return category.baykearticlecontent_set.all()

    @staticmethod
    def get_tag_articles(tag):
        """
        获取标签下的文章

        Args:
            tag: BaykeArticleTags 实例

        Returns:
            QuerySet: 文章查询集
        """
        return tag.baykearticlecontent_set.all()

    @staticmethod
    def get_user_articles(user):
        """
        获取用户的文章

        Args:
            user: User 实例

        Returns:
            QuerySet: 文章查询集
        """
        return user.baykearticlecontent_set.all()

    @staticmethod
    def create_article_pv_uv(request, article):
        """
        创建文章PV/UV记录并返回文章对象

        Args:
            request: HttpRequest对象
            article: 文章对象

        Returns:
            BaykeArticleContent: 文章对象
        """
        Visit.objects.create_pv_uv(request, article)
        return article

    @staticmethod
    def get_article_by_pk(pk, queryset=None):
        """
        根据主键获取文章

        Args:
            pk: 文章主键
            queryset: 基础查询集

        Returns:
            BaykeArticleContent: 文章对象
        """
        if queryset is None:
            queryset = BaykeArticleContent.objects.all()
        return queryset.get(pk=pk)

    @staticmethod
    def get_article_list_queryset():
        """
        获取文章列表的基础查询集

        Returns:
            QuerySet: 文章查询集，按创建时间倒序排列
        """
        return BaykeArticleContent.objects.all().order_by('-created_time')

    @staticmethod
    def get_archive_months():
        """
        获取文章归档月份列表

        Returns:
            QuerySet: 月份查询集
        """
        return BaykeArticleContent.objects.dates(field_name="created_time", kind="month")

    @staticmethod
    def get_paginated_articles(queryset, page_number=1, per_page=10):
        """
        获取分页后的文章列表

        Args:
            queryset: 文章查询集
            page_number: 页码
            per_page: 每页数量

        Returns:
            Page: 分页对象
        """
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page_number)
        return page_obj

    @staticmethod
    def get_sidebar_data():
        """
        获取侧边栏数据

        Returns:
            dict: 包含侧边栏相关数据的字典
        """
        sidebar_items = BaykeSidebar.objects.filter(is_show=True).order_by('order')

        # 获取常用数据
        categories = BaykeArticleCategory.objects.filter(parent__isnull=True)
        tags = BaykeArticleTags.objects.all()[:20]  # 限制数量
        archive_months = BaykeArticleContent.objects.dates(
            field_name="created_time", kind="month"
        )[:12]  # 最近12个月

        return {
            'sidebar_items': sidebar_items,
            'categories': categories,
            'tags': tags,
            'archive_months': archive_months,
        }