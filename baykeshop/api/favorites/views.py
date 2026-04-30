from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baykeshop.contrib.shop.services.favorite_service import FavoriteService


class FavoriteToggleView(APIView):
    """收藏/取消收藏切换"""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'write'

    def post(self, request):
        goods_id = request.data.get('goods_id')
        if not goods_id:
            return Response(
                {'success': False, 'message': '请提供商品ID'},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        page = int(request.query_params.get('page', 1))
        result = FavoriteService.get_user_favorites(request.user, page_number=page, per_page=20)
        return Response(result)
