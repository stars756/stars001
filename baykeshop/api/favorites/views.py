from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baykeshop.contrib.shop.services.favorite_service import FavoriteService

from .serializers import FavoriteListSerializer, FavoriteToggleSerializer


class FavoriteToggleView(APIView):
    """收藏/取消收藏切换"""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'write'

    def post(self, request):
        serializer = FavoriteToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        goods_id = serializer.validated_data['goods_id']

        if FavoriteService.is_favorited(request.user, goods_id):
            result = FavoriteService.remove_favorite(request.user, goods_id)
            result['favorited'] = False
        else:
            result = FavoriteService.add_favorite(request.user, goods_id)
            result['favorited'] = True

        result['count'] = FavoriteService.get_favorites_count(request.user)
        return Response(result)


class FavoriteListView(APIView):
    """收藏列表"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = FavoriteListSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        page = serializer.validated_data['page']

        result = FavoriteService.get_user_favorites(request.user, page_number=page, per_page=20)
        return Response(result)
