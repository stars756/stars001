from django.contrib.auth import get_user_model
from django.views.generic import ListView, MonthArchiveView
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.utils.translation import gettext_lazy as _
# Create your views here.
from baykeshop.contrib.article.models import BaykeArticleCategory, BaykeArticleTags, BaykeArticleContent
from baykeshop.contrib.article.services.article_service import ArticleService

# Create your views here.

User = get_user_model()


class BaykeArticleContentListView(ListView):
    """ 全部文章 """
    model = BaykeArticleContent
    template_name = 'baykeshop/article/list.html'
    paginate_by = 10
    ordering = ['-created_time']

    def get_queryset(self):
        """获取文章列表查询集"""
        return ArticleService.get_article_list_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('全部文章')
        return context


class BaykeArticleSearchView(BaykeArticleContentListView):
    """ 搜索 """
    def get_queryset(self):
        query = self.request.GET.get('q')
        queryset = super().get_queryset()
        return ArticleService.search_articles(queryset, query)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.request.GET.get('q', '')
        return context


class BaykeArticleCategoryListView(SingleObjectMixin, ListView):
    """ 分类文章 """
    model = BaykeArticleContent
    template_name = 'baykeshop/article/list.html'
    paginate_by = 10
    ordering = ['-created_time']

    def get(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=BaykeArticleCategory.objects.all())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return ArticleService.get_category_articles(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.object.name
        return context


class BaykeArticleTagsListView(SingleObjectMixin, ListView):
    """ 标签文章 """
    model = BaykeArticleContent
    template_name = 'baykeshop/article/list.html'
    paginate_by = 10
    ordering = ['-created_time']

    def get(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=BaykeArticleTags.objects.all())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return ArticleService.get_tag_articles(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.object.name
        return context


class BaykeArticleContentDetailView(DetailView):
    """ 文章详情 """
    model = BaykeArticleContent
    template_name = 'baykeshop/article/detail.html'
    context_object_name = 'article'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        return ArticleService.create_article_pv_uv(self.request, obj)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.object.title
        return context
    

class BaykeArticleArchiveView(MonthArchiveView):
    """ 归档 """
    date_field = 'created_time'
    template_name = 'baykeshop/article/list.html'
    allow_empty = True
    make_object_list = True
    month_format = '%m'
    paginate_by = 10

    def get_queryset(self):
        return ArticleService.get_article_list_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('文章归档')
        return context
    

class BaykeArticleUserListView(SingleObjectMixin, ListView):
    """ 用户文章 """
    model = BaykeArticleContent
    template_name = 'baykeshop/article/list.html'
    paginate_by = 10
    ordering = ['-created_time']

    def get(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=User.objects.all())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return ArticleService.get_user_articles(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"{self.object.username} 的文章"
        return context