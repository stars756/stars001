"""商品 API 视图"""
from django.core.paginator import Paginator
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from baykeshop.contrib.shop.models import BaykeShopCategory, BaykeShopGoods
from baykeshop.contrib.shop.services.comment_service import CommentService
from .serializers import CategorySerializer, GoodsDetailSerializer, GoodsListSerializer


class GoodsListView(GenericAPIView):
    """商品列表 — 分页 + 分类筛选 + 搜索"""
    permission_classes = [AllowAny]
    serializer_class = GoodsListSerializer

    def get(self, request):
        category_id = request.query_params.get('category')
        keyword = request.query_params.get('q', '').strip()
        page = int(request.query_params.get('page', 1))

        qs = BaykeShopGoods.objects.filter(status=BaykeShopGoods.Status.ONLINE)
        if category_id:
            qs = qs.filter(category__id=category_id)
        if keyword:
            qs = qs.filter(name__icontains=keyword)

        qs = qs.order_by('-created_time')
        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(page)
        serializer = self.get_serializer(page_obj.object_list, many=True)
        return Response({
            'results': serializer.data,
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page,
        })


class GoodsDetailView(GenericAPIView):
    """商品详情"""
    permission_classes = [AllowAny]
    serializer_class = GoodsDetailSerializer

    def get(self, request, goods_id):
        try:
            goods = BaykeShopGoods.objects.get(id=goods_id, status=BaykeShopGoods.Status.ONLINE)
        except BaykeShopGoods.DoesNotExist:
            return Response({'detail': '商品不存在'}, status=404)

        serializer = self.get_serializer(goods)
        data = serializer.data
        data['score_avg'] = CommentService.get_score_avg(goods)
        data['comment_count'] = CommentService.get_comment_count(goods)
        return Response(data)


class CategoryListView(GenericAPIView):
    """分类树"""
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer

    def get(self, request):
        categories = BaykeShopCategory.objects.filter(parent__isnull=True, is_nav=True)
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)
