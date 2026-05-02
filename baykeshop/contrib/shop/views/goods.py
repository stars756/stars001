from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView
from django.views.generic.detail import DetailView, SingleObjectMixin

from baykeshop.contrib.shop.models import BaykeShopCategory, BaykeShopGoods
from baykeshop.contrib.shop.services.goods_service import GoodsService


class BaykeShopGoodsListView(ListView):
    """商品列表"""
    template_name = 'baykeshop/shop/list.html'
    paginate_by = 20
    model = BaykeShopGoods
    ordering = ('-created_time',)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "商品列表"
        context['breadcrumbs'] = [{'name': _('商品列表'), 'url': None}]
        return context

    def get_queryset(self):
        # 优化N+1查询：预取商品关联的分类、SKU、图片等数据
        queryset = super().get_queryset().select_related('brand').prefetch_related(
            'category',
            'baykeshopgoodssku_set',
            'baykeshopgoodsimages_set'
        )
        return self.filter_queryset(queryset)

    def filter_queryset(self, queryset):
        return GoodsService.filter_goods_queryset(queryset, self.request.GET.dict())


class BaykeShopCategoryListView(SingleObjectMixin, BaykeShopGoodsListView):
    """商品分类列表"""
    def get(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=BaykeShopCategory.objects.all())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return GoodsService.get_category_goods(self.object, self.request.GET.dict())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.object.name
        context['breadcrumbs'] = [
            {'name': _('商品列表'), 'url': reverse('shop:list')},
            {'name': self.object.name, 'url': None},
        ]
        return context


class BaykeShopGoodsDetailView(DetailView):
    """商品详情"""
    model = BaykeShopGoods
    template_name = 'baykeshop/shop/detail.html'
    context_object_name = 'spu'

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs.get(self.pk_url_kwarg)
        if pk is not None:
            goods = GoodsService.get_goods_spu_detail(pk)
            if goods is not None:
                # 缓存命中也需确认商品未被物理删除
                try:
                    BaykeShopGoods.objects.get(pk=goods.pk)
                except BaykeShopGoods.DoesNotExist:
                    GoodsService.update_goods_spu_detail_cache(pk)
                    raise Http404(f'商品不存在 (id={pk})')
                return goods

            try:
                goods = super().get_object(queryset)
            except Http404:
                GoodsService.update_goods_spu_detail_cache(pk)
                raise Http404(f'商品不存在 (id={pk})')
            GoodsService.get_goods_spu_detail(pk, default=goods)
            return goods

        return super().get_object(queryset)

    def get(self, request, *args, **kwargs):
        GoodsService.create_pv_uv(request, self.get_object())
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        goods = self.get_object()
        context['title'] = goods.name
        context['images'] = GoodsService.get_goods_images(goods)
        context['recommends'] = GoodsService.get_recommend_goods(goods)
        context['comments'] = GoodsService.get_goods_comments(goods, self.request.GET.get('page', 1))
        context['score_avg'] = GoodsService.get_goods_score_avg(goods)
        context['like_score'] = GoodsService.get_goods_like_score(goods)
        context['comments_count'] = GoodsService.get_goods_comments_count(goods)
        context['breadcrumbs'] = [
            {'name': _('商品列表'), 'url': reverse('shop:list')},
            {'name': goods.name, 'url': None},
        ]
        return context




class BaykeShopSearchView(BaykeShopGoodsListView):
    """商品搜索"""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "商品搜索"
        context['breadcrumbs'] = [{'name': _('商品搜索'), 'url': None}]
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = self.request.GET.get("keyword")
        return GoodsService.search_goods(queryset, keyword, self.request.GET.dict())
