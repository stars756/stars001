from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _

from baykeshop.contrib.common.mixins import BaykeLoginRequiredMixin
from baykeshop.contrib.shop.services.favorite_service import FavoriteService


class BaykeShopFavoritesView(BaykeLoginRequiredMixin, TemplateView):
    """我的收藏"""
    template_name = 'baykeshop/member/favorites.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = int(self.request.GET.get('page', 1))
        result = FavoriteService.get_user_favorites(self.request.user, page_number=page, per_page=20)
        context['title'] = _('我的收藏')
        context['favorites'] = result.get('favorites', [])
        context['total'] = result.get('total', 0)
        context['page'] = result.get('page', page)
        context['total_pages'] = result.get('total_pages', 1)
        context['page_range'] = range(1, context['total_pages'] + 1)
        return context
